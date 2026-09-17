import os.path
import json
import pandas as pd
from datetime import datetime, timedelta
from runeq import initialize
from source.checkers.api.base import BaseAPIChecker
from runeq.resources.patient import get_patient, get_device
from runeq.resources.client import Config, StreamClient, GraphClient
from runeq.resources.stream import get_stream_data
from runeq.resources.stream_metadata import get_patient_stream_metadata, get_stream_metadata
from runeq.resources.stream_metadata import StreamMetadataSet
import shutil
from pathlib import Path
from time import time
from runeq.resources.client import global_graph_client, global_stream_client
import csv
from io import StringIO


class RuneAPICheckerMixin(BaseAPIChecker):

    'Saves by measurement category'

    #: Duration before the current date-time to search for new data, as a pandas frequency string

    look_back_duration = None # default is None (will pull all historic data), but can be overwritten in the config file (format e.g. "14D")
    categories = ['sleep', 'motion', 'vitals', 'device_info', 'environment']

    def clean(self):
        path = self.source_location['path']
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)  # remove file or symlink
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)  # remove directory
            except Exception as e:
                self.warn(f'Failed to delete {file_path}. Reason: {e}')
        pass

    checker_name = "RuneAPIChecker"
    day_resolution = int(pd.Timedelta(days=1).total_seconds())

    _state = []

    def setup_clients(self):
        """Prepare both the metadata and stream data clients for use by this checker"""
        # Load the Rune config from the specified rune config file
        initialize(self.source_location['rune_config'])
        rune_config = Config(self.source_location['rune_config'])
        # These will be set directly on the ParserCommon class.
        # TODO: Is there a better way to safely store these? without using rune's globals.
        self.stream_client = StreamClient(rune_config)
        self.graph_client = GraphClient(rune_config)

    def check_streams(self, patient_stream_data, start_date):
        """
        Check whether there is any new data for a specific patient.

        Parameters
        ----------
        patient_stream_data : object
            An object with a `.to_dataframe()` method producing a DataFrame
            containing at least the columns ['id', 'min_time', 'max_time', 'category'].
        start_date : str or datetime
            Earliest timestamp (inclusive) to fetch data from; enforced as a lower bound
            on `logged_end`.

        Returns
        -------
        pandas.DataFrame
            Subset of the merged streams DataFrame containing only rows where
            `max_time > logged_end` and `category` is in self.categories.
        """
        # 1) Parse and enforce the start_date boundary
        start_ts = pd.to_datetime(start_date).timestamp()

        # 2) Load previous state and convert incoming streams to DataFrame
        logs = self.load_state()
        streams_df = patient_stream_data.to_dataframe()

        # 3) Build a log_df of last successful 'logged_end' per stream
        if not logs.get('success'):
            log_df = pd.DataFrame(columns=['id', 'logged_end'])
        else:
            log_df = (
                pd.DataFrame(logs['success'])
                .sort_values('logged_end')
                .drop_duplicates(subset='id', keep='last')
            )

        # 4) Merge to get a working DataFrame with min_time, max_time, category, and logged_end
        merged_df = streams_df.merge(
            log_df[['id', 'logged_end']],
            on='id',
            how='left'
        )

        # 5) Fill missing logged_end with min_time
        merged_df['logged_end'] = merged_df['logged_end'].fillna(merged_df['min_time'])

        # 6) Enforce the user-specified start_date
        merged_df['logged_end'] = merged_df['logged_end'].clip(lower=start_ts)

        # 7) Optionally enforce a look-back duration if configured
        if self.look_back_duration:
            days = int(self.look_back_duration.rstrip('D'))
            look_back_ts = (datetime.utcnow() - timedelta(days=days)).timestamp()
            merged_df['logged_end'] = merged_df['logged_end'].clip(lower=look_back_ts)

        # 8) Filter for any streams where there is new data
        filtered_df = merged_df[merged_df['max_time'] > merged_df['logged_end']]

        # 9) Keep only the categories of interest
        filtered_df = filtered_df[filtered_df['category'].isin(self.categories)]

        # 10) Log if nothing to do, otherwise record how many streams will update
        if filtered_df.empty:
            patient_id = streams_df['patient_id'].iloc[0] if 'patient_id' in streams_df.columns else '<unknown>'
            self.warn(f"No new data for patient {patient_id}")
        self.log(f"{len(filtered_df)} streams getting updated out of {len(merged_df)}")

        return filtered_df

    def deduplication(self, df):
        'deduplicating stream data'
        # 1) Remove duplicate rows, ignoring the 'id' column
        cols_for_duplicates = [col for col in df.columns if col not in ['id','stream_type','parameters']]
        new_data_df = df.drop_duplicates(subset=cols_for_duplicates, keep='first')

        # 2) Remove any rows where source_device == 'unspecified'
        new_data_df = new_data_df[new_data_df['source_device'] != 'unspecified']

        return new_data_df

    def save_daily_stream_data(self, stream, stream_metadata, patient_name):
        """
        Given stream metadata, pull and save stream data from each day
        Return list of files for upload for given stream
        """
        start_ts = stream['logged_end']
        end_ts = stream['max_time'] 
        # Convert to Pandas Timestamps, then “floor” or “ceil” to whole days
        start_day = pd.to_datetime(start_ts, unit='s').floor('D')
        end_day = pd.to_datetime(end_ts, unit='s').ceil('D')

        file_list = []

        logs = self.load_state()

        # Walk day by day in [start_day, end_day)
        current_day = start_day
        while current_day < end_day:
            next_day = current_day + pd.Timedelta(days=1)

            # Fetch data for this one-day window
            try:
                day_data = stream_metadata.get_stream_dataframe(
                    start_time=int(current_day.timestamp()),
                    end_time=int(next_day.timestamp()),
                )
            except:
                continue

            # Only save if we actually have rows (not just an empty/header-only DataFrame)
            if not day_data.empty:  # e.g. day_data.shape[0] > 0
                # Format the date (YYYY-MM-DD) for folder naming, etc.
                day_str = current_day.strftime('%Y-%m-%d')

                # Build output folder path: [root]/[patient_name]/[day_str]
                out_path = os.path.join(
                    self.source_location['path'],
                    patient_name,
                    'rune',
                    day_str,
                    stream['measurement']
                )
                os.makedirs(out_path, exist_ok=True)

                # Choose the filename: e.g. "tremor_<stream_id>.csv"
                out_file = os.path.join(
                    out_path, 
                    f"{stream['source_device']}_{stream['id']}.csv"
                )

                file_list.append(out_file)

                # Write CSV
                day_data.to_csv(out_file, index=False)
                self.debug(f"Wrote {len(day_data)} rows to {out_file}.")

            # Move to the next day
            current_day = next_day

        return file_list # passes on list of files for the uploader (for a single stream)

    def check(self):
        """
        Search for new data from the RUNE API
        """
        self.setup_clients()
        tasks = []
        failures = []

        with open(self.source_location['rune_patients_config'], 'r') as file:
            rune_patients_config = json.load(file)


        for patient_name, patient_id in rune_patients_config['patient_ids'].items():
            try:
                patient = get_patient_stream_metadata(patient_id, client=self.graph_client)
            except Exception as e:
                error_dict = {
                    "type": "checker failure",
                    "location": "RuneAPICheckerMixin: get_patient",
                    "error": str(e),
                }
                failures.append(error_dict)
            else:               
                start_date = rune_patients_config['start_dates'][patient_name]
                new_data_df = self.check_streams(patient, start_date)
                if new_data_df.empty:
                    pass
                new_data_df = self.deduplication(new_data_df)

                for i, stream in new_data_df.iterrows():
                    try:
                        meta = get_stream_metadata(stream_ids=stream['id'])
                    except Exception as e:
                        error_dict = {
                            "type": "checker failure",
                            "location": "RuneAPICheckerMixin: get_stream_metadata",
                            "stream_metadata": stream,
                            "error": str(e),
                        }
                        failures.append(error_dict)
                    else:
                        stream_tasks = self.save_daily_stream_data(stream, meta, patient_name)
                        self._state.append({
                            'id':stream['id'],
                            'logged_end':stream['max_time'],
                            'timestamp':datetime.now(),
                            'failed_dates':[]
                        })
                        tasks.extend(stream_tasks)

        return {'to do': tasks, 'failure': failures}

    def save(self, completed):
        """Log which new time periods of RUNE data have been uploaded"""
        # Extract failures from completed
        failure_paths = completed.get('failure', [])

        # Process each failed file path
        for path in failure_paths:
            try:
                # Extract date (YYYY-MM-DD) from the directory in the path
                parts = path.split(os.sep)
                date_str = next((p for p in parts if p.count('-') == 2 and len(p) == 10), None)
                
                # Extract stream_id from the filename
                filename = os.path.basename(path)
                stream_id = filename.split('_')[-1]  # Assuming stream_id is the last part of filename
                
                if date_str and stream_id:
                    # Find the corresponding _state entry
                    state_entry = next((entry for entry in self._state if entry['id'] == stream_id), None)
                    
                    if state_entry:
                        # Append unique failed date
                        if date_str not in state_entry['failed_dates']:
                            state_entry['failed_dates'].append(date_str)

            except Exception as e:
                self.warn(f"Error processing path {path}: {e}")

        state = self.load_state()
        state['success'].extend(self._state)
        state['failure'].extend(completed['failure'])

        # Convert datetime objects in _state to ISO format before saving
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()  # Convert datetime to string
            raise TypeError(f"Type {type(obj)} not serializable")

        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(state, log, indent=2, default=convert_datetime) 


class SensorKitAPIChecker(BaseAPIChecker):
    """
    Checks for new Apple Sensorkit datasets by patient
    Split csv/json data into daily files for dates within look_back_duration
    """

    checker_name = "SensorKitAPIChecker"
    look_back_duration = "7D"
    dataset_page_size = 5000
    daily_timezone = "America/Chicago"

    dataset_query = """
        query getDataSessions($patient_id: ID!, $cursor: Cursor, $limit: Int!) {
            patient(id: $patient_id) {
                dataSessionList(cursor: $cursor, limit: $limit) {
                    pageInfo { endCursor }
                    dataSessions {
                        id
                        created_at: createdAt
                        schema_id: schemaId
                        streams { name: streamName }
                    }
                }
            }
        }
    """

    def iter_patient_datasets(self, patient_id, client):
        """List metadata in memory; the raw listing has no server-side date filter."""
        cursor, seen_cursors = None, set()
        page_count = 0
        while True:
            result = client.execute(statement=self.dataset_query, patient_id=patient_id,
                                    cursor=cursor, limit=self.dataset_page_size)
            page = result["patient"]["dataSessionList"]
            yield from page["dataSessions"]
            page_count += 1
            if page_count % 10 == 0:
                self.info(f"SensorKit metadata lookup: {page_count} pages read")
            cursor = page["pageInfo"]["endCursor"]
            if not cursor:
                return
            if cursor in seen_cursors:
                raise RuntimeError("Dataset API returned a repeated pagination cursor")
            seen_cursors.add(cursor)

    def daily_parts(self, content, first_day, last_day):
        """Keep whole records in their recording day, within the requested dates based on look_back_duration.

        Preserve Apple-epoch timestamps and original fields, including nested JSON.
        Intervals spanning midnight stay intact, assigned by their timestamp.
        """
        text = content.decode("utf-8-sig")
        if not text.strip():
            return []
        is_json = text.lstrip().startswith(("[", "{"))
        if is_json:
            rows = json.loads(text)
            if not isinstance(rows, list):
                raise ValueError("Expected a SensorKit JSON array of records")
            timestamps = [row["timestamp"] for row in rows]
        else:
            reader = csv.reader(StringIO(text), strict=True)
            header = next(reader)
            if header.count("timestamp") != 1 or len(set(header)) != len(header):
                raise ValueError("Expected CSV with one timestamp column and unique headers")
            rows = [row for row in reader if row]
            if any(len(row) != len(header) for row in rows):
                raise ValueError("SensorKit CSV row does not match its header")
            timestamp_column = header.index("timestamp")
            timestamps = [row[timestamp_column] for row in rows]
        if not rows:
            return []
        # Apple SensorKit uses seconds since 2001-01-01. 
        dates = pd.to_datetime(pd.to_numeric(timestamps, errors="raise") + 978307200,
                               unit="s", utc=True, errors="raise")
        if dates.isna().any():
            raise ValueError("Missing SensorKit timestamp; cannot assign a recording day")
        groups = {}
        for day, row in zip(dates.tz_convert(self.daily_timezone).strftime("%Y-%m-%d"), rows):
            if first_day <= day <= last_day:
                groups.setdefault(day, []).append(row)
        parts = []
        for day, records in sorted(groups.items()):
            if is_json:
                payload = json.dumps(records, ensure_ascii=False).encode()
            else:
                output = StringIO(newline="")
                writer = csv.writer(output)
                writer.writerow(header)
                writer.writerows(records)
                payload = output.getvalue().encode()
            parts.append((day, "json" if is_json else "csv", payload))
        return parts

    def check(self):
        days = pd.Timedelta(self.look_back_duration) / pd.Timedelta(days=1)
        if not 0 < days < float("inf") or not days.is_integer():
            raise ValueError("look_back_duration must be a positive whole number of days")
        now = pd.Timestamp(time(), unit="s", tz=self.daily_timezone)
        start = now.normalize() - pd.DateOffset(days=int(days) - 1)
        first_day, last_day = start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
        self.info(f"SensorKit recording days: {first_day} through {last_day} "
                  f"inclusive ({self.daily_timezone})")

        initialize(self.source_location["rune_config"])
        graph_client, stream_client = global_graph_client(), global_stream_client()
        with open(self.source_location["rune_patients_config"]) as file:
            patients = json.load(file)["patient_ids"]
        root = Path(self.source_location["path"])
        successes = self.load_successes()
        known_files = {entry["filename"] for entry in successes}
        # Reuse completion records only for the same timezone and a covered window.
        completed_sources = {entry["sensorkit_source"] for entry in successes
                             if entry.get("sensorkit_timezone") == self.daily_timezone
                             and entry.get("sensorkit_first_day", "9999") <= first_day}
        # Track all daily files from each raw stream so a partial copy remains retryable.
        self._source_files = {}
        self._first_day = first_day
        tasks, failures, seen = [], [], set()

        for patient, patient_id in patients.items():
            total = selected = already_uploaded = 0
            patient_task_count = len(tasks)
            try:
                patient_folder = root / patient / "sensorkit"
                for dataset in self.iter_patient_datasets(patient_id, graph_client):
                    total += 1
                    schema = dataset["schema_id"]
                    if "sensorkit" not in schema.lower():
                        continue
                    # Creation time selects candidate uploads; record timestamps select days.
                    if not start.timestamp() <= dataset["created_at"] <= now.timestamp():
                        continue
                    selected += 1
                    for stream in dataset["streams"]:
                        name = stream["name"]
                        if name.lower() == "metadata":
                            continue  # Do not download, stage, or upload metadata streams.
                        basename = f"{name}_{dataset['id']}"
                        source_id = str(patient_folder / schema / basename)
                        if source_id in seen:
                            continue
                        seen.add(source_id)
                        if source_id in completed_sources:
                            already_uploaded += 1
                            continue
                        try:
                            with stream_client._get(
                                f"{stream_client.config.stream_url}/v1/session",
                                params={"session_id": dataset["id"], "stream_name": name},
                            ) as response:
                                parts = self.daily_parts(response.content, first_day, last_day)
                            # All data types share the same daily folder.
                            outputs = [(patient_folder / day / f"{basename}.{extension}", payload)
                                       for day, extension, payload in parts]
                            self._source_files[source_id] = {str(path) for path, _ in outputs}
                            for path, payload in outputs:
                                filename = str(path)
                                if filename in known_files:
                                    continue
                                path.resolve().relative_to(root.resolve())
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_bytes(payload)
                                tasks.append(filename)
                                known_files.add(filename)
                        except Exception as error:
                            failures.append(self.download_failure(source_id, error))
            except Exception as error:
                failures.append(self.download_failure(str(root / patient), error))
            self.info(f"{patient}: {total} metadata records scanned; {selected} recent SensorKit datasets; "
                      f"{already_uploaded} streams already uploaded; {len(tasks) - patient_task_count} daily files staged")
        return {"to do": tasks, "failure": failures}

    def download_failure(self, filename, error):
        self.warning(f"SensorKit check failed for {filename}: {error}")
        return {"type": "checker failure", "filename": filename,
                "error": str(error), "timestamp": time()}

    def save(self, completed):
        """Use standard file events; mark a stream complete only after every copy succeeds."""
        state = self.load_state()
        state["success"] = [entry for entry in state["success"]
                            if entry.get("type") != "scan checkpoint"]
        state["success"].extend(completed["success"])
        state["failure"] = completed["failure"]
        state["skipped"] = completed.get("skipped", [])
        state = self.clean_outdated(state)

        uploaded = {entry["filename"]: entry for entry in state["success"]}
        for source_id, filenames in self._source_files.items():
            if filenames <= uploaded.keys():
                for filename in filenames:
                    uploaded[filename].update(sensorkit_source=source_id,
                                              sensorkit_first_day=self._first_day,
                                              sensorkit_timezone=self.daily_timezone)
        self.write_state(state)

    def clean(self):
        """Keep staged daily files; no extra cache files are created."""
        pass
