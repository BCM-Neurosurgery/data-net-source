import os
import json
import re
import time
from asyncio.staggered import staggered_race
from logging import ERROR, FileHandler

import pandas as pd
import requests

from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

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
    def fetch_collection_data(self, collection, headers, *, patient=None):
        """Perform the requests to the OuraAPI to get all the available data for a particular collection"""

    def _log_collection_error(self, patient, collection, reason):
        """Keep the study ID in the local file, out of monitoring and root handlers."""
        message = f"collection={collection}: {reason}"
        for logger in self.loggers:
            if logger.name != "file" or patient is None:
                logger.error(f"Oura {message}")
            elif logger.isEnabledFor(ERROR):
                record = logger.makeRecord(
                    logger.name, ERROR, __file__, 0, f"Oura patient={patient} {message}", (), None
                )
                for handler in logger.handlers:
                    if isinstance(handler, FileHandler) and handler.level <= ERROR:
                        handler.handle(record)

    def _log_http_error(self, patient, collection, response):
        """Extract a missing scope without logging the API response body."""
        reason = f"HTTP {response.status_code}"
        if response.status_code in (401, 403):
            try:
                detail = response.json()["detail"]
            except (ValueError, KeyError, TypeError):
                detail = None
            if isinstance(detail, str):
                match = re.fullmatch(r"Token is not authorized access ([a-z][a-z0-9_]{0,31}) scope\.?", detail)
                if match:
                    reason += f" missing_scope={match[1]}"
        self._log_collection_error(patient, collection, reason)

    def _fetch_pages(self, collection, headers, params, patient):
        """Return a complete result or None; never stage a partial response."""
        url = f"{self.api_url}/{collection}"
        params = dict(params)
        rows, seen = [], set()
        while True:
            try:
                response = requests.request("GET", url, headers=headers, params=params, timeout=30)
                if response.status_code != 200:
                    self._log_http_error(patient, collection, response)
                    return None
                body = response.json()
            except (requests.RequestException, ValueError) as exc:
                self._log_collection_error(patient, collection, f"request failed ({type(exc).__name__})")
                return None

            page = body.get("data") if isinstance(body, dict) else None
            if not isinstance(page, list):
                self._log_collection_error(patient, collection, "expected a data list")
                return None
            rows.extend(page)
            cursor = body.get("next_token")
            if cursor is None or cursor == "":
                return rows
            if not isinstance(cursor, str) or cursor in seen:
                self._log_collection_error(patient, collection, "invalid or repeated pagination token")
                return None
            seen.add(cursor)
            params["next_token"] = cursor

    def cross_check(self, patient, collection, found_data):
        """Check the found data against the saved log of data to find any newly uploaded data"""

        # Events have a start day; ring configuration is an undated snapshot.
        metadata = collection == "ring_configuration"
        date_key = "start_day" if collection in {"enhanced_tag", "rest_mode_period"} else "day"
        date_organized = {}
        for doc in found_data:
            doc_id = doc.get("id") if isinstance(doc, dict) else None
            doc_date = doc.get(date_key) if isinstance(doc, dict) else None
            try:
                valid_date = metadata or date.fromisoformat(doc_date).isoformat() == doc_date
            except (TypeError, ValueError):
                valid_date = False
            if not isinstance(doc_id, str) or not doc_id or not valid_date:
                fields = "id" if metadata else f"{date_key} and id"
                self._log_collection_error(patient, collection, f"expected {fields}; skipping this batch")
                return {}
            date_organized.setdefault(None if metadata else doc_date, []).append(doc)

        if metadata or not date_organized:
            return date_organized
        with open(os.path.join(self.state_path, 'upload_state.json')) as state_file:
            upload_state = json.load(state_file)

        # Compare document ids with the list of saved document ids, day by day
        new_data = {}
        for doc_date, day_data in date_organized.items():
            uploaded = [
                upload
                for upload in upload_state['success']
                if upload['patient'] == patient
                and upload['collection'] == collection
                and upload['date'] == doc_date
            ]
            # We found no matching data for this day, so upload by default
            if not uploaded:
                new_data[doc_date] = day_data
                continue

            # Get all the previously uploaded document ids for this day
            uploaded_docs = []
            for upload in uploaded:
                uploaded_docs.extend(upload['documents'])

            # There are more documents for this day than we uploaded before
            if len(uploaded_docs) < len(day_data):
                new_data[doc_date] = day_data
                continue

            # Check all the doc ids individually
            found_new = False
            for doc in day_data:
                if doc['id'] not in uploaded_docs:
                    new_data[doc_date] = day_data
                    found_new = True
                    break
            if found_new:
                continue

            # We only reach this point if there is nothing new to upload
            self.debug(f'No new data to upload for {doc_date}')

        return new_data

    def check(self):
        """
        Oura does not support a good way for querying new data. So we need to download the data and parse it locally
        """
        self.format_today()

        all_paths = []
        for patient, token in self.patients.items():
            headers = {'Authorization': f'Bearer {token}', 'User-Agent': 'data-net-source'}

            for collection in self.source_location['collections']:
                all_oura_data = self.fetch_collection_data(collection, headers, patient=patient)
                if not all_oura_data:
                    continue
                new_data = self.cross_check(patient, collection, all_oura_data)

                for day, day_data in new_data.items():
                    out_dir = os.path.join(self.source_location['path'], patient)
                    os.makedirs(out_dir, exist_ok=True)
                    name = f'{collection}_{day}.json' if day else f'{collection}.json'
                    filepath = os.path.join(out_dir, name)
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
        event_time_utc = pd.Timestamp(payload["event_time"], tz="UTC")
        event_time_local = event_time_utc.tz_convert(ZoneInfo("America/Chicago")).isoformat()
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
        payload_out["event_time"] = event_time_local  # optional but useful

        # choose a date for grouping (best effort)
        payload_out["date"] = (
            payload_out.get("day")
            or payload_out.get("summary_date")
            or (event_time_local[:10] if isinstance(event_time_local, str) and len(event_time_local) >= 10 else None)
            or timestamp_clean[:10]  # from filename like YYYY-MM-DD...
        )

        event_id = f"{object_id}_{event_time_local}"

        # Save the downloaded data in the local staging directory for further processing
        stage_dir = self.local_staging_path / participant_id / data_type
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged_file = stage_dir / f"{event_id}.json"
        with open(staged_file, "w") as f:
            f.write(json.dumps(payload_out, indent=2))

        event_payload = {
            "patient_id": participant_id,
            "doc_type": self.event_track_datatype,   # "webhook_times"
            "date": payload_out["date"],             # same day grouping
            "id": event_id,          # unique per webhook file (good enough)
            "data_type": data_type,
            "object_id": object_id,
            "event_time": event_time_local,
            "event_type": payload.get("event_type"),
            "user_id": user_id,
        }

        event_dir = self.local_staging_path / participant_id / self.event_track_datatype
        event_dir.mkdir(parents=True, exist_ok=True)
        event_file = event_dir / f"{event_id}.json"
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

    def fetch_collection_data(self, collection, headers, *, patient=None):
        """Fetch a complete date range, or an undated ring configuration snapshot."""
        params = {}
        if collection != "ring_configuration":
            params = {
                "start_date": (self.today - pd.Timedelta(self.look_back_duration)).strftime("%Y-%m-%d"),
                "end_date": self.today.strftime("%Y-%m-%d"),
            }
        return self._fetch_pages(collection, headers, params, patient)


class OuraAPIStreamChecker(OuraAPIBaseChecker):
    """
    Checker to pull down data from oura that is saved as individual datapoints instead of documents

    Works by reformatting all the data found in the stream as day-shape documents
    Only compatible with legacy (pre-OAuth2) versions od the Oura API
    """
    checker_name = "OuraAPIDocumentChecker"

    def fetch_collection_data(self, collection, headers, *, patient=None):
        """Fetch every chunk before producing UTC-day files."""
        time_fmt = "%Y-%m-%dT%H:%M:%SZ"
        start = (self.today - pd.Timedelta(self.look_back_duration)).normalize()
        end = self.today + pd.Timedelta(days=1)
        by_day = {}
        while start < end:
            stop = min(start + pd.Timedelta(days=28), end)
            params = {
                "start_datetime": start.strftime(time_fmt),
                "end_datetime": stop.strftime(time_fmt),
            }
            points = self._fetch_pages(collection, headers, params, patient)
            if points is None:
                return []
            for point in points:
                try:
                    timestamp = datetime.fromisoformat(point["timestamp"].replace("Z", "+00:00"))
                    if timestamp.utcoffset() is None:
                        raise ValueError("missing timezone")
                    timestamp = timestamp.astimezone(timezone.utc)
                except (KeyError, TypeError, AttributeError, ValueError):
                    self._log_collection_error(patient, collection, "invalid sample timestamp; skipping this batch")
                    return []
                if start <= timestamp < stop:
                    # Keep distinct samples and ignore exact repeats from the API.
                    encoded = json.dumps(point, sort_keys=True)
                    by_day.setdefault(timestamp.date().isoformat(), {})[timestamp, encoded] = point
            start = stop

        documents = []
        for day, points in sorted(by_day.items()):
            keys = sorted(points)
            # Battery values can change without changing the sample count.
            if collection == "ring_battery_level":
                digest = sha256("\n".join(encoded for _, encoded in keys).encode()).hexdigest()
                doc_id = f"{day}:{digest}"
            else:
                doc_id = f"{day}:n-points:{len(keys)}"
            documents.append({"day": day, "id": doc_id, "data": [points[key] for key in keys]})
        return documents


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
      - uses stream logic for timestamped heart rate and battery samples
      - uses document logic for everything else
    """
    checker_name = "OuraOAuthAllChecker"

    # Which collections should use stream logic
    stream_collections = {"heartrate", "ring_battery_level"}

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

    def fetch_collection_data(self, collection, headers, *, patient=None):
        """
        Dispatch to existing fetch logic depending on collection.
        """
        # Make sure the reused impl objects see the same runtime state/settings
        self._sync_impl(self._doc_impl)
        self._sync_impl(self._stream_impl)

        if collection in self.stream_collections:
            return self._stream_impl.fetch_collection_data(collection, headers, patient=patient)
        else:
            return self._doc_impl.fetch_collection_data(collection, headers, patient=patient)

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
        impl.loggers = self.loggers
        # If your framework logger methods are instance methods on BaseChecker:
        impl.debug = self.debug
        impl.info = self.info
        impl.error = self.error
        # impl.notify = self.notify
        impl.log = getattr(self, "log", self.info)
