import os.path
import json
import pandas as pd
from datetime import datetime, timedelta
from runeq import initialize
initialize()

from source.checkers.api.base import BaseAPIChecker
from runeq.resources.patient import get_patient, get_device
from runeq.resources.client import Config, StreamClient, GraphClient
from runeq.resources.stream import get_stream_data
from runeq.resources.stream_metadata import get_patient_stream_metadata, get_stream_metadata
from runeq.resources.stream_metadata import StreamMetadataSet
import shutil


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
                print(f'Failed to delete {file_path}. Reason: {e}')
        pass

    checker_name = "RuneAPIChecker"
    day_resolution = int(pd.Timedelta(days=1).total_seconds())

    _state = []

    def setup_clients(self):
        """Prepare both the metadata and stream data clients for use by this checker"""
        # Load the Rune config from the specified rune config file
        rune_config = Config(self.source_location['rune_config'])

        # These will be set directly on the ParserCommon class.
        # TODO: Is there a better way to safely store these? without using rune's globals.
        self.stream_client = StreamClient(rune_config)
        self.graph_client = GraphClient(rune_config)

    def check_streams(self, patient_stream_data):
        """Check whether there is any new data for a specific patient"""
        logs = self.load_state()
        
        # Ensure log_df exists with required columns
        if not logs.get('success'):
            log_df = pd.DataFrame(columns=['id', 'logged_end'])
        else:
            log_df = pd.DataFrame(logs['success'])
            log_df = log_df.sort_values('logged_end').drop_duplicates(subset='id', keep='last') # pick out maximum log time per stream

        streams_df = patient_stream_data.to_dataframe()

        # Merge device stream metadata with the upload_state data to then filter out old data to check
        merged_df = streams_df.merge(
            log_df[['id', 'logged_end']],
            left_on='id',
            right_on='id',
            how='left'
        )

        if self.look_back_duration:
            look_back_days = int(self.look_back_duration[:-1])  # Extract number of days
            look_back_timestamp = (datetime.utcnow() - timedelta(days=look_back_days)).timestamp()
        else:
            look_back_timestamp = merged_df['logged_end'].min()

        # if the last log time is earlier than the look_back_timestamp, replace it with the look_back_timestamp
        # print(merged_df)
        # print(look_back_timestamp)
        self.log(f'{merged_df['logged_end'].count()} streams with new data out of {len(merged_df['logged_end'])}')
        print(f'{merged_df['logged_end'].count()} streams with new data out of {len(merged_df['logged_end'])}')
        
        merged_df['logged_end'].mask(merged_df['logged_end'] < look_back_timestamp, look_back_timestamp, inplace=True)
        # Replace NaN values in 'logged_end' with the look-back timestamp: if there is no upload state, go by look back duration
        merged_df['logged_end'].fillna(look_back_timestamp, inplace=True)

        # Filtering only for new data
        filtered_df = merged_df[
            merged_df['max_time'] > merged_df['logged_end']
        ]
        
        filtered_df = filtered_df[filtered_df['category'].isin(self.categories)]

        if filtered_df.empty:
            self.info(f"No info available for patient {patient_stream_data['patient_id'].iloc[0]}")  
        
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


        for patient_name, patient_id in rune_patients_config[self.project_name].items():
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
                new_data_df = self.check_streams(patient)
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
                            'log_time':datetime.now(),
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
                print(f"Error processing path {path}: {e}")

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
