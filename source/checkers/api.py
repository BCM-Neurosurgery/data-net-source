import pandas as pd
import numpy as np
import requests

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
                    new_streams.append({
                        'stream_id': stream_data['id'],
                        'time_range': [logged_end, stream_end],
                    })
            device_todo = {
                'time_range': [logged_end, device_end],
                'name': device.name,
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

        active_devices = [d for d in all_devices if d.id not in log['deactivated_devices']]

        if not active_devices:
            return {}   # No active devices therefore there is no new data to return

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


class OuraAPIChecker(BaseChecker):

    checker_name = "OuraAPIChecker"
    api_url = 'https://api.ouraring.com/v2/usercollection/'

    #: Names of the data types to download from Oura
    collections = []

    #: Dict of patient IDs and the API keys for each patient
    patient_meta = {
        'patient_id': [
            'timestamp',   # Start: Date when patient data was first collected.
            'timestamp',   # End: Date when the patients data stopped being collected. Leave None to use today
            'LONGAPIKEY',  # APIKEY: Key set by Oura to access this patients data through the API
        ]
    }

    def check(self):
        all_patients = {}
        for patient, (start, end, token) in self.patient_meta:
            headers = {'Authorization': f'Bearer {token}'}

            end = pd.Timestamp.today() if end is None else end
            date_range = pd.date_range(start=start, end=end, freq='7D')

            all_collections = {}
            for collection in self.collections:

                all_docs = []
                collection_url = f'https://api.ouraring.com/v2/usercollection/{collection}'
                for i in range(len(date_range)-1):

                    params = {
                        'start_datetime': date_range[i].strftime('%Y-%m-%dT%H:%M:%S%z'),
                        'end_datetime': date_range[i+1].strftime('%Y-%m-%dT%H:%M:%S%z'),
                    }
                    response = requests.request('GET', collection_url, headers=headers, params=params)

                    doc_ids = [documents['id'] for documents in response.json()['data']]
                    all_docs.extend(doc_ids)

                all_collections[collection] = all_docs
            all_patients[patient] = all_collections

    def save(self, completed):
        pass

    def clean(self):
        pass