import os.path

import pandas as pd
import numpy as np
import requests
import json
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


class OuraAPIDocumentChecker(BaseChecker):
    """
    This class is only compatible with data stored by the API as 'documents'.

    Datatypes that are not stored like this have to be handled by a separate parser.
    """

    checker_name = "OuraAPIChecker"

    api_url = 'https://api.ouraring.com/v2/usercollection/'

    source_location = {
        #: Names of the data types to download from Oura
        'collections': [],

        # Dict of patient IDs and the API keys for each patient
        'patients': {
            'patient_id': 'LONGAPIKEY',
        },
        'interim': 'location/to/store/downloaded/data'
    }

    def fetch_collection_data(self, patient, collection, date_range, headers):
        """Find and download all the JSON data for a single collection of a single patient"""
        collection_url = f'https://api.ouraring.com/v2/usercollection/{collection}'
        all_out_paths = []

        # Iterate over the date ranges to get all documents for this collection, saving these data batches
        for i in range(len(date_range) - 1):
            start_date = date_range[i].strftime('%Y-%m-%d')
            params = {
                'start_datetime': start_date,
                'end_datetime': date_range[i + 1].strftime('%Y-%m-%d'),
            }
            response = requests.request('GET', collection_url, headers=headers, params=params)

            # Save the data we just downloaded to the local disk for parsing into usable JSONS
            out_path = os.path.join(self.middle_location, 'download', patient, f'{collection}_{start_date}.json')
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w') as json_out:
                json.dump(response.json(), json_out)
            all_out_paths.append(out_path)

        return all_out_paths

    def check(self):
        """
        Oura does not support a good way for querying new data. So we need to download the data and parse it locally
        """
        for patient, (start, end, token) in self.patient_meta.items():
            headers = {'Authorization': f'Bearer {token}'}

            # We will get documents in large batches to reduce the number of API requests
            start = pd.Timestamp(start)
            end = pd.Timestamp.today() if end is None else pd.Timestamp(end)
            date_range = pd.date_range(start=start, end=end, freq='20D')

            all_paths = {}
            for collection in self.collections:
                saved = self.fetch_collection_data(patient, collection, date_range, headers)
                all_paths[(patient, collection)] = saved

        return {'to do': all_paths, 'failure': []}

    def save(self, completed):
        pass

    def clean(self):
        pass