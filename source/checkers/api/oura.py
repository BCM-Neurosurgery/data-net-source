import os
import json

import pandas as pd
import requests

from abc import abstractmethod, ABC

from source.checkers.api.base import BaseAPIChecker


class OuraAPIBaseChecker(BaseAPIChecker, ABC):

    api_url = 'https://api.ouraring.com/v2/usercollection'

    source_location = {
        #: Names of the data types to download from Oura
        'collections': [],
        # Dict of patient IDs and the API keys for each patient
        'patients': {
            'patient_id': 'LONGAPIKEY',
        }
    }

    look_back_duration = '1D'
    today = None

    _time_parameter_name = None

    def format_today(self):
        """Ensure that the variable for today is saved as a pd.Timestamp, setting to current system date otherwise"""
        if self.today is None:
            self.today = pd.Timestamp.today()
        else:
            self.today = pd.Timestamp(self.today)

    @abstractmethod
    def fetch_collection_data(self, collection, headers):
        """Perform the requests to the OuraAPI to get all the available data for a particular collection"""

    def cross_check(self, patient, collection, found_data):
        """Check the found data against the saved log of data to find any newly uploaded data"""

        with open(
            os.path.join(self.state_path, 'upload_state.json')
        ) as state_file:
            upload_state = json.load(state_file)

        # Organize the documents for this collection by day
        date_organized = {}
        for doc in found_data:
            doc_date = doc['day']
            if doc_date not in date_organized:
                date_organized[doc_date] = [doc]
            else:
                date_organized[doc_date].append(doc)

        # Compare document ids with the list of saved document ids, day by day
        new_data = {}
        for date, day_data in date_organized.items():
            uploaded = [
                upload
                for upload in upload_state['success']
                if upload['patient'] == patient
                and upload['collection'] == collection
                and upload['date'] == date
            ]
            # We found no matching data for this day, so upload by default
            if not uploaded:
                new_data[date] = day_data
                continue

            # Get all the previously uploaded document ids for this day
            uploaded_docs = []
            for upload in uploaded:
                uploaded_docs.extend(upload['documents'])

            # There are more documents for this day than we uploaded before
            if len(uploaded_docs) < len(day_data):
                new_data[date] = day_data
                continue

            # Check all the doc ids individually
            found_new = False
            for doc in day_data:
                if doc['id'] not in uploaded_docs:
                    new_data[date] = day_data
                    found_new = True
                    break
            if found_new:
                continue

            # We only reach this point if there is nothing new to upload
            self.notify(f'No new data to upload for {date}')

        return new_data

    def check(self):
        """
        Oura does not support a good way for querying new data. So we need to download the data and parse it locally
        """
        self.format_today()

        all_paths = []
        for patient, token in self.patients.items():
            headers = {'Authorization': f'Bearer {token}'}

            for collection in self.source_location['collections']:
                all_oura_data = self.fetch_collection_data(collection, headers)
                new_data = self.cross_check(patient, collection, all_oura_data)

                for day, day_data in new_data.items():
                    out_dir = os.path.join(self.source_location['path'], patient)
                    os.makedirs(out_dir, exist_ok=True)
                    filepath = os.path.join(out_dir, f'{collection}_{day}.json')
                    with open(filepath, 'w') as day_json:
                        json.dump(day_data, day_json)
                    all_paths.append(filepath)

        return {'to do': all_paths, 'failure': []}

    def save(self, completed):
        pass

    def clean(self):
        pass


class OuraAPIDocumentChecker(OuraAPIBaseChecker):
    """
    This class is only compatible with data stored by the API as 'documents'.

    Datatypes that are not stored like this have to be handled by a different checker.

    Source Format:
    {
        "collections": [],  # List of modality names, as defined by the OuraAPI to pull documents for
        "patients": {       # Dictionary of patient IDs and the API keys needed to access that patient's data
            "patient_id": "OuraAPI-patient-application-key"
        }
    }

    Other Settings:
      - look_back_duration: (optional) pandas frequency string, defines how far back from the current date to look for
      new documents. By default, this is 14D, since the OuraRing can store up to two weeks of data locally.
      - today: (optional) pandas date defining the current date, mainly used for testing purposes. Leave as None to use
      the real current date.
      - api_url: (optional) the full URL needed to access the OuraRing REST API.

    """

    checker_name = "OuraAPIDocumentChecker"
    _time_parameter_name = 'date'

    def fetch_collection_data(self, collection, headers):
        """Find and download all the JSON data for a single collection of a single patient"""
        collection_url = f'{self.api_url}/{collection}'

        # Get all documents for this collection between now and the look back duration
        start_date = self.today - pd.Timedelta(self.look_back_duration)
        today = self.today.strftime('%Y-%m-%d')
        params = {
            f'start_{self._time_parameter_name}': start_date.strftime('%Y-%m-%d'),
            f'end_{self._time_parameter_name}': today,
        }
        response = requests.request(
            'GET', collection_url, headers=headers, params=params
        )

        if response.status_code != 200:
            # Per Oura ring docs any response code besides 200 should be an error
            self.error(f'Oura returned an error code ({response.status_code})')
            return {}

        return response.json()['data']


class OuraAPIStreamChecker(OuraAPIBaseChecker):
    """
    Checker to pull down data from oura that is saved as individual datapoints instead of documents

    Works by reformatting all the data found in the stream as day-shape documents
    """
    checker_name = "OuraAPIDocumentChecker"
    _time_parameter_name = 'datetime'

    def fetch_collection_data(self, collection, headers):
        """Find and download all the JSON data for a single collection of a single patient"""
        collection_url = f'{self.api_url}/{collection}'
        time_fmt = '%Y-%m-%dT00:00:00'

        start_date = self.today - pd.Timedelta(self.look_back_duration)
        days = pd.date_range(start=start_date, end=self.today, freq='D')

        all_data = []

        day_intervals = zip(days[:-1], days[1:])
        # Get all documents for this collection between now and the look back duration
        for day, next_day in day_intervals:
            # TODO: how do we need to treat timezones???
            params = {
                f'start_{self._time_parameter_name}': day.strftime(time_fmt),
                f'end_{self._time_parameter_name}': next_day.strftime(time_fmt),
            }
            response = requests.request(
                'GET', collection_url, headers=headers, params=params
            )

            if response.status_code != 200:
                # Per Oura ring docs any response code besides 200 should be an error
                self.error(f'Oura returned an error {response.status_code} for {collection} when fetching {day}')
            elif not response.json()['data']:
                self.error(f'Oura returned an empty dataset')
            else:
                day_str = day.strftime('%Y-%m-%d')
                stream_data = response.json()['data']
                day_data = {
                    'day': day_str,
                    'id': f'{day_str}:n-points:{len(stream_data)}',
                    'data': stream_data
                }
                all_data.append(day_data)

        return all_data