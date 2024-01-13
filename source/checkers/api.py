import pandas as pd
import numpy as np

import runeq
from runeq.resources import patient as rune_patient
from runeq.resources import stream_metadata as rune_metadata

from source.checkers.base import BaseChecker


class RuneAPICheckerMixin(BaseChecker):

    checker_name = "RuneAPIChecker"
    day_resolution = int(pd.Timedelta(days=1).total_seconds())

    def check_device(self, device, device_log):
        device_streams = rune_metadata.get_patient_stream_metadata(device.patient_id, device.id)
        device_meta = device_streams.to_dataframe()
        device_end = max(device_meta['max_time'])

        logged_end = device_log[-1]['max_time']

        if logged_end > device_end:
            new_streams = []
            for i, stream_data in device_meta.iterrows():
                stream_end = stream_data['max_time']
                if stream_end > logged_end:
                    new_streams.append({
                        'stream_id': stream_data['id'],
                        'time_range': [logged_end, stream_end],
                    })
            device_todo = {
                'time_range': [logged_end, device_end],
                'streams': new_streams
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

        active_devices = [d for d in all_devices if d not in log['deactivated_devices']]

        if not active_devices:
            return {}   # No active devices therefore there is no new data to return

        else:
            rune_todo = {}
            successes = self.load_success_log()
            for device in active_devices:
                device_log = successes[device.id] if device.id in successes else {}
                device_todo = self.check_device(device, device_log)
                rune_todo[device.id] = device_todo
            return rune_todo


    def save(self, completed):
        """Log which new time periods of RUNE data have been uploaded"""
        pass
