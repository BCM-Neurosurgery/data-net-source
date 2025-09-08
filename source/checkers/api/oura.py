import os
import json
from asyncio.staggered import staggered_race

import pandas as pd
import requests

from datetime import datetime
from pathlib import Path

import toml
from paramiko import SSHClient 

from abc import abstractmethod, ABC

from source.checkers.api.base import BaseAPIChecker
from source.checkers.base import BaseChecker

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
    

class OuraWebhookChecker(BaseChecker):
    """

    """

    checker_name = "OuraChecker"

    # Optional settings for where to find data on the remote listener server
    #
    webhook_post_folder_name = 'webhook_posts'
    webhook_post_folder_path = None

    participant_map_file_name = 'participant_map.json'
    participant_map_file_path = None

    auth_token_file_name = 'oura_tokens.json'
    auth_token_file_path = None

    # Name of file in staging to keep track of the most recent event for each patient
    event_track_datatype = 'webhook_times'

    oura_api_url = "https://api.ouraring.com/v2/usercollection"

    stub_config = """
    [parser.init.source]
    # Path on the remote system hosting the listener server to look for new data
    listener_data = ''
    # Local path where data downloaded based on listener's events will be placed
    path = ''
      
      # Information needed to open an ssh/sftp connection to the listener server
      [parser.init.source.ssh_config]
      hostname = 'path.to.remote'
      username = 'your-username'
      password = 'your-password'
    """
    source_location = toml.loads(stub_config)

    @property
    def source_data_path(self):
        return Path(self.source_location['listener_data'])

    def build_remote_path(self, fullpath, ending):
        if fullpath:  # Prefer full explicit path if given
            return fullpath
        else:
            return Path(self.source_data_path / ending)

    @property
    def webhook_post_path(self):
        return self.build_remote_path(self.webhook_post_folder_path, self.webhook_post_folder_name)

    @property
    def participant_map_path(self):
        return self.build_remote_path(self.participant_map_file_path, self.participant_map_file_name)

    @property
    def auth_token_path(self):
        return self.build_remote_path(self.auth_token_file_path, self.auth_token_file_name)

    @property
    def local_staging_path(self):
        return Path(self.source_location["path"])

    def make_connection(self):
        self.info("Connecting to remote SSH...")
        ssh_config = self.source_location.get("ssh_config")
        self.sftp = None

        # Set up the ssh client
        if ssh_config is not None:
            self.ssh = SSHClient()
            self.ssh.load_system_host_keys()
            self.ssh.connect(hostname=ssh_config["hostname"],
                             username=ssh_config["username"],
                             key_filename=ssh_config["key_filename"])
            self.sftp = self.ssh.open_sftp()

    def close_connection(self):
        self.sftp.close()
        self.ssh.close()

    def _read_json_file(self, path):
        """Read in the contents of a json file remotely via SSH/SFTP"""
        with self.sftp.open(path, "r") as f:
            return json.load(f)

    def _map_user_to_participant(self, user_id):
        try:
            user_map = self._read_json_file(self.participant_map_path.as_posix())
        except IOError:
            raise FileNotFoundError(f"Could not find participant_map ({self.participant_map_path.as_posix()})")

        try:
            mapped_id = user_map[user_id]
        except KeyError:
            self.debug(f'User ID {user_id} not found in the participant map')
            raise KeyError("Could not find user!")  # Make sure user IDs are not sent via error logging
        else:
            self.debug(f"User ID: {user_id}, mapped participant: {mapped_id}")
        return mapped_id

    def iter_webhooks(self):
        user_dirs = self.sftp.listdir(self.webhook_post_path.as_posix())
        self.info(f"Users found in webhook dir:  {user_dirs}")
        for user in user_dirs:
            user_path = Path(self.webhook_post_path, user)
            modality_dirs = self.sftp.listdir(user_path.as_posix())
            for modality in modality_dirs:
                modality_path = Path(user_path, modality)
                webhooks_jsons = [f for f
                                  in self.sftp.listdir(modality_path.as_posix())
                                  if f.endswith(".json")]
                for filename in webhooks_jsons:
                    yield Path(modality_path, filename), filename

    def process_webhooks(self):
        # pass the state variables from function to function -> potentially avoiding self.?
        to_process = []
        failures = []

        # Load tokens for all patients from the webhook server
        token_path = self.auth_token_path
        tokens = self._read_json_file(token_path.as_posix())

        for file_path, filename in self.iter_webhooks():
            try:
                payload = self._read_json_file(file_path.as_posix())
                results = self._handle_payload(payload, tokens, filename)
            except Exception as e:
                import sys, traceback
                self.warning(f"[ERROR] Failed on {file_path}: {str(e)}")
                failures.append({
                    "file": file_path,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.now().timestamp()
                })
            else:
                to_process.extend(results)
        return to_process, failures

    def _handle_payload(self, payload, tokens, timestamp_clean):
        data_type = payload["data_type"]
        user_id = payload["user_id"]
        object_id = payload["object_id"]
        event_time = payload["event_time"]

        # TODO: need to correctly mark successful uploads only here

        # Map between oura IDs and study-ids, also fetch relevant access tokens
        # (Missing values will cause a key error which should crash back to calling function)
        participant_id = self._map_user_to_participant(user_id)
        token = tokens[participant_id]["access_token"]

        # Retrieve the data for this document from the Oura API
        url = f"{self.oura_api_url}/{data_type}/{object_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)
        self.debug(f"Queried {url} for {participant_id}/{data_type}: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        # Save the downloaded data in the local staging directory for further processing
        stage_dir = self.local_staging_path / participant_id / data_type
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged_file = stage_dir / timestamp_clean
        with open(staged_file, "w") as f:
            f.write(json.dumps(data, indent=2))

        staged_files = [staged_file]

        # Update the time of the most recent event for this patient in the event time tracker
        patient_event_file = self.local_staging_path / participant_id / self.event_track_datatype / timestamp_clean
        if os.path.exists(patient_event_file):
            with open(patient_event_file, "r") as f:
                existing_event_times = json.load(f)
        else:
            existing_event_times = {}

        if data_type in existing_event_times:
            existing_event_times[data_type] = existing_event_times[data_type] + event_time
        else:
            existing_event_times[data_type] = event_time

        # If an event time was updated make sure the event tracker file is appended to the list
        with open(patient_event_file, "w") as f:
            json.dump(existing_event_times, f, indent=2)
            staged_files.append(patient_event_file)

        return staged_files

    # find new webhook posts that haven't been processed and query the api for the data 
    def check(self):

        try:
            self.make_connection()
            to_process, failures = self.process_webhooks()
        except Exception as e:
            raise e
        finally:
            self.close_connection()

        # Make sure to upload files are unique (since there could be multiple even tracker updates)
        to_process = list(set(to_process))

        self.info(f'Found data from new webhook events!')
        self.info(f'Experienced {len(failures)} failures during data retrieval')
        return {"to do": to_process, "failure": failures}

    def save(self, completed):
        to_save = completed.get("success", [])
        if to_save:
            self.info(f"[Save] to_save contents: {to_save[0]}") 

        self.info(f"[Save] Marking {len(to_save)} files as uploaded")

        for item in to_save:
            self.upload_state["success"].append({
                "key": item["key"],
                "uploaded": item["uploaded"],
                "timestamp": item["timestamp"]
            })

        # write once after all are added
        with open(self.state_path, "w") as f:
            json.dump(self.upload_state, f, indent=2)

    def clean(self):
        if not hasattr(self, "sftp"):
            self.make_connection()
        with open(self.state_path, "r") as f:
            self.upload_state = json.load(f)
        
        # clean outdated log entries
        cleaned_log = super().clean_outdated(self.upload_state)

        # delete old uploaded files
        final_log = super().clean_old_success(cleaned_log)

        # save cleaned upload log
        with open(self.state_path, "w") as f:
            json.dump(final_log, f, indent=2)

