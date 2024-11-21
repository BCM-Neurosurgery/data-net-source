import os.path

import pandas as pd

from source.checkers.api.base import BaseAPIChecker
from runeq.resources.patient import get_patient, get_device
from runeq.resources.client import Config, StreamClient, GraphClient
from runeq.resources.stream import get_stream_data

class RuneAPICheckerMixin(BaseAPIChecker):

    #: Duration before the current date-time to search for new data, as a pandas frequency string
    look_back_duration = '14D'

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

    def check_device(self, device):
        """Check whether there is any new data for a specific device"""
        device_log = self.filter_device_logs(device)

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
        self.setup_clients()
        tasks = []

        for patient_name, patient_config in self.patients.items():
            patient = get_patient(patient_config["rune_id"], client=self.graph_client)
            for device_id in patient_config["active_devices"]:
                device = get_device(patient, device_id, client=self.graph_client)

                new_data = self.check_device(device)

                for data_section in new_data:

                    start_time = pd.Timestamp(data_section["date"])
                    end_time = start_time + pd.Timedelta('1D')

                    dataframe = pd.DataFrame(get_stream_data(
                        stream_id=data_section['stream_id'],
                        start_time=start_time.timestamp(),
                        end_time=end_time.timestamp(),
                        client=self.stream_client
                    ))
                    out_path = os.path.join(
                        self.source_location['path'],
                        patient_name, data_section['date']
                    )
                    os.makedirs(out_path, exist_ok=True)
                    out_file = os.path.join(out_path, f'{device.name}.csv')
                    dataframe.to_csv(out_file)

        return {'todo': tasks, 'failure': []}


    def save(self, completed):
        """Log which new time periods of RUNE data have been uploaded"""
        pass
