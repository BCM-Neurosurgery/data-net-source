import os.path

import pandas as pd
import numpy as np
import requests
import json


from source.checkers.base import BaseChecker


class RuneAPICheckerMixin(BaseChecker):

    checker_name = "RuneAPIChecker"
    day_resolution = int(pd.Timedelta(days=1).total_seconds())

    def check_device(self, device, device_log):
        device_streams = rune_metadata.get_patient_stream_metadata(
            device.patient_id, device.id
        )
        device_meta = device_streams.to_dataframe()
        try:
            device_end = max(device_meta['max_time'])
        except KeyError as e:
            if device_meta.empty:
                self.info(f'No info available for {device.id}: {device.name}')
                return {}
            else:
                raise e

        logged_end = device_log[-1]['max_time'] if device_log else 0

        if device_end > logged_end:
            new_streams = []
            for i, stream_data in device_meta.iterrows():
                stream_end = stream_data['max_time']
                if stream_end > logged_end:
                    new_streams.append(
                        {
                            'stream_id': stream_data['id'],
                            'time_range': [logged_end, stream_end],
                        }
                    )
            device_todo = {
                'time_range': [logged_end, device_end],
                'name': device.name,
                'streams': new_streams,
            }

        else:
            device_todo = {}
        return device_todo

    def check(self):
        """
        Search for new data from the RUNE API
        NOTE: the source location for this is ignored
        """
        runeq.initialize()

        # First get all available patients and devices
        all_devices = rune_patient.get_all_devices()

        log = self.load_log()

        active_devices = [
            d for d in all_devices if d.id not in log['deactivated_devices']
        ]

        if not active_devices:
            return {}  # No active devices therefore there is no new data to return

        else:
            rune_todo = {}
            successes = self.load_success_log()
            for device in active_devices:
                device_log = successes[device.id] if device.id in successes else {}
                device_todo = self.check_device(device, device_log)
                if device_todo:
                    rune_todo[device.id] = device_todo
            return rune_todo

    def save(self, completed):
        """Log which new time periods of RUNE data have been uploaded"""
        pass


class OuraAPIDocumentChecker(BaseChecker):
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

    checker_name = "OuraAPIChecker"

    api_url = 'https://api.ouraring.com/v2/usercollection'

    source_location = {
        #: Names of the data types to download from Oura
        'collections': [],
        # Dict of patient IDs and the API keys for each patient
        'patients': {
            'patient_id': 'LONGAPIKEY',
        }
    }

    look_back_duration = '14D'
    today = pd.Timestamp('2023-07-05 00:00:00')

    def fetch_collection_data(self, collection, headers):
        """Find and download all the JSON data for a single collection of a single patient"""
        collection_url = f'{self.api_url}/{collection}'

        # Get all documents for this collection between now and the look back duration
        start_date = self.today - pd.Timedelta(self.look_back_duration)
        today = self.today.strftime('%Y-%m-%d')
        params = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': today,
        }
        response = requests.request(
            'GET', collection_url, headers=headers, params=params
        )

        if response.status_code != 200:
            # Per Oura ring docs any response code besides 200 should be an error
            self.error(f'Oura returned an error code ({response.status_code})')
            return {}

        return response.json()['data']

    def cross_check(self, patient, collection, found_data):
        """Check the found data against the saved log of data to find any newly uploaded data"""

        with open(
            os.path.join(self.middle_location['path'], 'upload_state.json')
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

        all_paths = []
        for patient, token in self.source_location['patients'].items():
            headers = {'Authorization': f'Bearer {token}'}

            for collection in self.source_location['collections']:
                all_oura_data = self.fetch_collection_data(collection, headers)
                new_data = self.cross_check(patient, collection, all_oura_data)

                for day, day_data in new_data.items():
                    out_dir = os.path.join(self.middle_location['path'], patient)
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
