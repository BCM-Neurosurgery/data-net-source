import os
import json
import time
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
        if self.today is None:
            self.today = pd.Timestamp.now(tz="UTC").normalize()
        else:
            self.today = pd.Timestamp(self.today)
            if self.today.tzinfo is None:
                self.today = self.today.tz_localize("UTC")
            else:
                self.today = self.today.tz_convert("UTC")
            self.today = self.today.normalize()

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


class OuraOAuthBaseChecker(BaseChecker, ABC):

    oura_api_url = "https://api.ouraring.com/v2/usercollection"

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


class OuraOAuthWebhookChecker(OuraOAuthBaseChecker):
    """
    Checker that connects to a remote server which is listening for webhooks from Oura,
    and fetches the specified data from the OuraAPI, authenticating via OAuth2
    """

    checker_name = "OuraOAuthWebhookChecker"

    # Optional settings for where to find data on the remote listener server
    webhook_post_folder_name = "webhook_posts"
    webhook_post_folder_path = None

    participant_map_file_name = "participant_map.json"
    participant_map_file_path = None

    auth_token_file_name = "oura_tokens.json"
    auth_token_file_path = None

    # Name of file in staging to keep track of the most recent event for each patient
    event_track_datatype = "webhook_times"

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

    def _json_safe(self, obj):
        """Recursively convert Path-like objects into JSON-serializable types."""
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, dict):
            return {k: self._json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._json_safe(v) for v in obj]
        return obj

    @property
    def source_data_path(self):
        return Path(self.source_location["listener_data"])

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

    def _map_user_to_participant(self, user_id):
        try:
            user_map = self._read_json_file(self.participant_map_path.as_posix())
        except IOError:
            raise FileNotFoundError(f"Could not find participant_map ({self.participant_map_path.as_posix()})")

        try:
            mapped_id = user_map[user_id]
        except KeyError:
            self.debug(f"User ID {user_id} not found in the participant map")
            raise KeyError("Could not find user!")  # Make sure user IDs are not sent via error logging
        else:
            self.debug(f"User ID: {user_id}, mapped participant: {mapped_id}")
        return mapped_id

    def iter_webhooks(self):
        """
        Generator yielding (remote_file_path, filename).

        NOTE: Kept original structure, but now includes a fast look_back_duration cutoff
        using lexicographic comparison of the filename timestamp.
        """
        # Fast cutoff string for filenames: "YYYY-MM-DDTHH-MM-SS"
        start_cutoff = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(self.look_back_duration)).strftime(
            "%Y-%m-%dT%H-%M-%S"
        )

        user_dirs = self.sftp.listdir(self.webhook_post_path.as_posix())
        self.info(f"Users found in webhook dir:  {user_dirs}")

        for user in user_dirs:
            user_path = Path(self.webhook_post_path, user)
            modality_dirs = self.sftp.listdir(user_path.as_posix())

            for modality in modality_dirs:
                modality_path = Path(user_path, modality)

                webhooks_jsons = [f for f in self.sftp.listdir(modality_path.as_posix()) if f.endswith(".json")]

                # NEW: sort newest-first so we can break early when we hit older-than-cutoff
                webhooks_jsons = sorted(webhooks_jsons, reverse=True)

                for filename in webhooks_jsons:
                    # filename looks like: "2026-03-11T10-29-08.json"
                    base = filename[:-5]  # strip ".json"
                    if base < start_cutoff:
                        # since sorted desc, everything else will be older too
                        break

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
                import traceback

                self.warning(f"[ERROR] Failed on {file_path}: {str(e)}")
                failures.append(
                    {
                        "file": file_path,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "timestamp": datetime.now().timestamp(),
                    }
                )
            else:
                to_process.extend(results)

        return to_process, failures

    def _handle_payload(self, payload, tokens, timestamp_clean):
        data_type = payload["data_type"]
        user_id = payload["user_id"]
        object_id = payload["object_id"]
        event_time = payload["event_time"]
        timestamp_base = Path(timestamp_clean).stem

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

        # --- required by JSONDocInjectorUploader ---
        payload_out = data if isinstance(data, dict) else {"data": data}

        payload_out["patient_id"] = participant_id
        payload_out["doc_type"] = data_type
        payload_out["document_id"] = object_id  # stable unique identifier
        payload_out["event_time"] = event_time  # optional but useful

        # choose a date for grouping (best effort)
        payload_out["date"] = (
            payload_out.get("day")
            or payload_out.get("summary_date")
            or (event_time[:10] if isinstance(event_time, str) and len(event_time) >= 10 else None)
            or timestamp_clean[:10]  # from filename like YYYY-MM-DD...
        )

        # Save the downloaded data in the local staging directory for further processing
        stage_dir = self.local_staging_path / participant_id / data_type
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged_file = stage_dir / f"{timestamp_base}.json"
        with open(staged_file, "w") as f:
            f.write(json.dumps(payload_out, indent=2))

        event_payload = {
            "patient_id": participant_id,
            "doc_type": self.event_track_datatype,   # "webhook_times"
            "date": payload_out["date"],             # same day grouping
            "document_id": timestamp_base,          # unique per webhook file (good enough)
            "data_type": data_type,
            "object_id": object_id,
            "event_time": event_time,
            "event_type": payload.get("event_type"),
            "user_id": user_id,
        }

        event_dir = self.local_staging_path / participant_id / self.event_track_datatype
        event_dir.mkdir(parents=True, exist_ok=True)
        event_file = event_dir / f"{timestamp_base}.json"
        with open(event_file, "w") as f:
            json.dump(event_payload, f, indent=2)

        staged_files = [staged_file.as_posix(), event_file.as_posix()]
        return staged_files

    # find new webhook posts that haven't been processed and query the api for the data
    def check(self):
        # NEW: make sure upload_state exists for save()/clean()
        self.upload_state = self.load_state()

        try:
            self.make_connection()
            to_process, failures = self.process_webhooks()
        except Exception as e:
            raise e
        finally:
            self.close_connection()

        # Make sure to upload files are unique (since there could be multiple even tracker updates)
        to_process = list(set(to_process))
        to_process = [str(p) for p in to_process]

        self.info("Found data from new webhook events!")
        self.info(f"Experienced {len(failures)} failures during data retrieval")
        return {"to do": to_process, "failure": failures}

    def save(self, completed):
        if not hasattr(self, "upload_state"):
            self.upload_state = self.load_state()

        successes = completed.get("success", []) or []
        failures = completed.get("failure", []) or []

        self.info(f"[Save] Marking {len(successes)} files as uploaded")
        self.info(f"[Save] Recording {len(failures)} failures")
        for item in successes:

            uploaded = item["filename"]
            ts = item.get("timestamp", time.time())

            record = {
                "uploaded": uploaded,
                "timestamp": ts,
            }
            self.upload_state.setdefault("success", []).append(record)

        self.upload_state.setdefault("failure", []).extend(failures)

        self.write_state(self.upload_state)

    def clean(self):
        if not hasattr(self, "sftp"):
            self.make_connection()

        # NEW: load upload_state from disk
        self.upload_state = self.load_state()

        # clean outdated log entries
        cleaned_log = super().clean_outdated(self.upload_state)

        # delete old uploaded files
        final_log = super().clean_old_success(cleaned_log)

        # save cleaned upload log
        self.write_state(final_log)


class OuraAPIDocumentChecker(OuraAPIBaseChecker):
    """
    This class is only compatible with data stored by the API as 'documents'.

    Only compatible with legacy (pre-OAuth2) versions od the Oura API
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
            self.error(f'Oura returned an error code ({response.status_code}): {response.text}')
            return {}

        return response.json()['data']


class OuraAPIStreamChecker(OuraAPIBaseChecker):
    """
    Checker to pull down data from oura that is saved as individual datapoints instead of documents

    Works by reformatting all the data found in the stream as day-shape documents
    Only compatible with legacy (pre-OAuth2) versions od the Oura API
    """
    checker_name = "OuraAPIDocumentChecker"
    _time_parameter_name = "datetime"

    def fetch_collection_data(self, collection, headers):
        """Find and download all the JSON data for a single collection of a single patient"""
        collection_url = f"{self.api_url}/{collection}"
        time_fmt = "%Y-%m-%dT%H:%M:%SZ"

        start_date = self.today - pd.Timedelta(self.look_back_duration)
        end_date = self.today + pd.Timedelta(days=1)  # include all of today

        chunk_days = 28

        all_points = []

        # iterate in 28-day chunks instead of by day: [chunk_start, chunk_end)
        chunk_start = start_date
        while chunk_start < end_date:
            chunk_end = min(chunk_start + pd.Timedelta(days=chunk_days), end_date)
            chunk_start.tz_convert("UTC")
            chunk_end.tz_convert("UTC")

            params = {
                f"start_{self._time_parameter_name}": chunk_start.strftime(time_fmt),
                f"end_{self._time_parameter_name}": chunk_end.strftime(time_fmt),
            }

            response = requests.request("GET", collection_url, headers=headers, params=params)

            if response.status_code != 200:
                self.error(
                    f"Oura returned an error {response.status_code} for {collection} "
                    f"for interval {chunk_start.date()} -> {chunk_end.date()}: {response.text}"
                )
                # choose behavior: either continue to next chunk or bail out
                # continuing is usually safer so you still get partial data
                chunk_start = chunk_end
                continue

            payload = response.json()
            points = payload.get("data", [])
            # self.debug(f"{collection} {chunk_start} -> {chunk_end}: {len(points)} points, payload keys={list(payload.keys())}")
            if not points:
                # not necessarily an error; often just no data in that interval
                chunk_start = chunk_end
                continue

            all_points.extend(points)
            chunk_start = chunk_end

        if not all_points:
            self.error("Oura returned an empty dataset across all chunks")
            return []

        # Group by date extracted from each datapoint timestamp
        ts_key = "timestamp"

        # 1) Pull timestamps once (same filtering behavior: missing -> skip)
        pts = [pt for pt in all_points if pt.get(ts_key)]
        ts_vals = [pt[ts_key] for pt in pts]

        # 2) Vectorized parse (WAY faster than per-row)
        ts = pd.to_datetime(ts_vals, utc=True, errors="coerce")

        # 3) Drop NaT (same behavior as your pd.isna(ts) continue)
        mask = ts.notna()
        pts = [p for p, ok in zip(pts, mask) if ok]
        ts = ts[mask]

        # 4) Day strings in one shot (also faster than per-row strftime)
        day_strs = ts.strftime("%Y-%m-%d")

        by_day = {}
        for pt, day_str in zip(pts, day_strs):
            by_day.setdefault(day_str, []).append(pt)

        # Build day-shaped docs
        all_data = []
        for day_str in sorted(by_day.keys()):
            pts_for_day = by_day[day_str]
            all_data.append({
                "day": day_str,
                "id": f"{day_str}:n-points:{len(pts_for_day)}",
                "data": pts_for_day,
            })

        self.log(f"all data len {len(all_data)}")
        return all_data


class OuraOAuthDocumentChecker(OuraOAuthBaseChecker, OuraAPIDocumentChecker):
    """
    Checker designed to periodically fetch data from Oura API, using OAuth tokens which are continuously refreshed
    on a separate server
    """
    checker_name = 'OuraOAuthDocumentChecker'

    stub_config = """
    [parser.init.source]
    # Path to JSON on the remote system hosting the OAuth refresh service where auth tokens are stored
    auth_token_file_path = ''
    # Local path where data downloaded will be cached for further processing
    path = ''
    # List of modalities to fetch from the Oura API
    collections = []

      # Information needed to open an ssh/sftp connection to the listener server
      [parser.init.source.ssh_config]
      hostname = 'path.to.remote'
      username = 'your-username'
      password = 'your-password'
    """
    source_location = toml.loads(stub_config)

    @property
    def patients(self):
        """Fetch active patient list and most current tokens from the OAuth service"""
        self.make_connection()
        patient_tokens = self._read_json_file(self.source_location['auth_token_file_path'])
        self.close_connection()
        simple_tokens = {patient: data['access_token'] for patient, data in patient_tokens.items()}
        return simple_tokens


class OuraOAuthStreamChecker(OuraOAuthBaseChecker, OuraAPIStreamChecker):
    """
    Checker designed to periodically fetch data from Oura API, using OAuth tokens which are continuously refreshed
    on a separate server
    """
    checker_name = 'OuraOAuthStreamChecker'

    auth_token_file_path = None

    stub_config = """
    [parser.init.source]
    # Path to JSON on the remote system hosting the OAuth refresh service where auth tokens are stored
    auth_token_file_path = ''
    # Local path where data downloaded will be cached for further processing
    path = ''
    # List of modalities to fetch from the Oura API
    collections = []

      # Information needed to open an ssh/sftp connection to the listener server
      [parser.init.source.ssh_config]
      hostname = 'path.to.remote'
      username = 'your-username'
      password = 'your-password'
    """
    source_location = toml.loads(stub_config)

    @property
    def patients(self):
        """Fetch active patient list and most current tokens from the OAuth service"""
        self.make_connection()
        patient_tokens = self._read_json_file(self.source_location['auth_token_file_path'])
        self.close_connection()
        simple_tokens = {patient: data['access_token'] for patient, data in patient_tokens.items()}
        return simple_tokens



class OuraOAuthAllChecker(OuraOAuthBaseChecker, OuraAPIBaseChecker):
    """
    Unified OAuth checker:
      - uses OAuth tokens (like OuraOAuthDocumentChecker / OuraOAuthStreamChecker)
      - uses stream logic for heartrate
      - uses document logic for everything else
    """
    checker_name = "OuraOAuthAllChecker"

    # Which collections should use stream logic
    stream_collections = {"heartrate"}

    # Reuse the existing implementations without modifying them
    _doc_impl = OuraOAuthDocumentChecker()
    _stream_impl = OuraOAuthStreamChecker()

    stub_config = """
    [parser.init.source]
    auth_token_file_path = ''
    path = ''
    collections = []

      [parser.init.source.ssh_config]
      hostname = 'path.to.remote'
      username = 'your-username'
      key_filename = '/path/to/key'
    """
    source_location = toml.loads(stub_config)["parser"]["init"]["source"]

    @property
    def patients(self):
        """Fetch active patient list and most current tokens from the OAuth service"""
        self.make_connection()
        patient_tokens = self._read_json_file(self.source_location["auth_token_file_path"])
        self.close_connection()
        return {patient: data["access_token"] for patient, data in patient_tokens.items()}

    def fetch_collection_data(self, collection, headers):
        """
        Dispatch to existing fetch logic depending on collection.
        """
        # Make sure the reused impl objects see the same runtime state/settings
        self._sync_impl(self._doc_impl)
        self._sync_impl(self._stream_impl)

        if collection in self.stream_collections:
            return self._stream_impl.fetch_collection_data(collection, headers)
        else:
            return self._doc_impl.fetch_collection_data(collection, headers)

    def _sync_impl(self, impl):
        """
        Copy the minimum state that the legacy fetchers expect.
        This avoids editing the original classes.
        """
        impl.api_url = self.api_url
        impl.today = self.today
        impl.look_back_duration = self.look_back_duration
        impl.state_path = self.state_path
        impl.source_location = self.source_location
        # If your framework logger methods are instance methods on BaseChecker:
        impl.debug = self.debug
        impl.info = self.info
        impl.error = self.error
        # impl.notify = self.notify
        impl.log = getattr(self, "log", self.info)
