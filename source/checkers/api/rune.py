import os.path

import pandas as pd
from datetime import datetime
from runeq import initialize
initialize()

from source.checkers.api.base import BaseAPIChecker
from runeq.resources.patient import get_patient, get_device
from runeq.resources.client import Config, StreamClient, GraphClient
from runeq.resources.stream import get_stream_data
from runeq.resources.stream_metadata import get_patient_stream_metadata, get_stream_metadata
from runeq.resources.stream_metadata import StreamMetadataSet

class RuneAPICheckerMixin(BaseAPIChecker):

    'Saves by measurement category'

    #: Duration before the current date-time to search for new data, as a pandas frequency string
    look_back_duration = '90D'
    categories = ['sleep', 'motion', 'vitals', 'device_info', 'environment']

    def clean(self):
        pass

    checker_name = "RuneAPIChecker"
    day_resolution = int(pd.Timedelta(days=1).total_seconds())

    def setup_clients(self):
        """Prepare both the metadata and stream data clients for use by this checker"""
        # Load the Rune config from the specified rune config file
        rune_config = Config(self.source_location['rune_config'])

        # These will be set directly on the ParserCommon class.
        # TODO: Is there a better way to safely store these? without using rune's globals.
        self.stream_client = StreamClient(rune_config)
        self.graph_client = GraphClient(rune_config)

    def filtered_device_logs(self, device):
        """"""
        all_logs = self.load_state()
        return all_logs

    def filter_streams(self, device_streams, logged_end):
        """Filter device_streams by categories and by log time"""

        def new_stream_data(stream) -> bool:
            """Return True if stream has data since last log"""
            return stream.max_time > logged_end
        
        device_streams = device_streams.filter(filter_function=new_stream_data)
        device_streams_update = StreamMetadataSet()
        for category in self.categories:
            category_streams = device_streams.filter(category=category)
            device_streams_update.update(category_streams)

        return device_streams_update

    def check_device(self, device):
        """Check whether there is any new data for a specific device"""
        device_log = self.filtered_device_logs(device)

        device_streams = get_patient_stream_metadata(
            device.patient_id, device.id
        )
        device_streams_df = device_streams.to_dataframe()
        
        try:
            device_end = max(device_streams_df['max_time'])
        except KeyError as e:
            if device_streams_df.empty:
                self.info(f'No info available for {device.id}: {device.name}')
                return {}
            else:
                raise e

        logged_end = device_log[-1]['max_time'] if device_log['success'] else min(device_streams_df['min_time']) # the last log is the last log time, else it is the earliest time of data collection

        if device_end > logged_end: # if there is new data since last upload, 
            device_streams = self.filter_streams(self, device_streams, logged_end) # filter device streams by category and time since last log
        else:
            device_streams = {}

        return device_streams # dataframe of stream ID's and their dates

    def deduplication(df):
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
        start_ts = stream['created_at'] - 1
        end_ts = stream['max_time'] + 1
        # Convert to Pandas Timestamps, then “floor” or “ceil” to whole days
        start_day = pd.to_datetime(start_ts, unit='s').floor('D')
        end_day = pd.to_datetime(end_ts, unit='s').ceil('D')

        file_list = []

        # Walk day by day in [start_day, end_day)
        current_day = start_day
        while current_day < end_day:
            next_day = current_day + pd.Timedelta(days=1)

            # Fetch data for this one-day window
            day_data = stream_metadata.get_stream_dataframe(
                start_time=int(current_day.timestamp()),
                end_time=int(next_day.timestamp()),
            )

            # Only save if we actually have rows (not just an empty/header-only DataFrame)
            if not day_data.empty:  # e.g. day_data.shape[0] > 0
                # Format the date (YYYY-MM-DD) for folder naming, etc.
                day_str = current_day.strftime('%Y-%m-%d')

                # Build output folder path: [root]/[patient_name]/[day_str]
                out_path = os.path.join(
                    self.source_location['path'],
                    patient_name,
                    day_str
                )
                os.makedirs(out_path, exist_ok=True)

                # Choose the filename: e.g. "tremor_<stream_id>.csv"
                out_file = os.path.join(
                    out_path, 
                    f"{stream['measurement']}_{stream['id']}.csv"
                )

                file_list.append(out_file)

                # Write CSV
                day_data.to_csv(out_file, index=False)
                self.debug(f"Wrote {len(day_data)} rows to {out_file}.")

            # Move to the next day
            current_day = next_day

    def check(self):
        """
        Search for new data from the RUNE API
        """
        self.setup_clients()
        tasks = []
        failures = []

        for patient_name, patient_config in self.patients.items():
            try:
                patient = get_patient(patient_config["rune_id"], client=self.graph_client)
            except Exception as e:
                error_dict = {
                    "type": "checker failure",
                    "location": "RuneAPICheckerMixin: get_patient",
                    "error": str(e),
                }
                failures.append(error_dict)
            else:
                for device_id in patient.devices:
                    try:
                        device = get_device(patient, device_id, client=self.graph_client)
                    except Exception as e:
                        error_dict = {
                            "type": "checker failure",
                            "location": "RuneAPICheckerMixin: get_device",
                            "error": str(e),
                        }
                        failures.append(error_dict)
                    else:                    
                        new_data = self.check_device(device)
                        if not new_data:
                            print('no new data for ',device_id)
                            continue
                        new_data_df = new_data.to_dataframe()
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
                                tasks.extend(stream_tasks)

        return {'to do': tasks, 'failure': failures}


    def save(self, completed):
        """Log which new time periods of RUNE data have been uploaded"""
        pass
