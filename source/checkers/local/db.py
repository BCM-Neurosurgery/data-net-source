import os
from datetime import datetime
import requests
import pandas as pd
from source.checkers.local import FileCheckerMixin

class DBFileCheckerMixin(FileCheckerMixin):
    db_url = ''
    dump_route = ''
    # look back duration as pandas timedelta str
    look_back_duration = '1D'
    container_path = ''
    actual_path = ''

    # by default gets data from midnight to 'look_back_duration' prior
    # method can be overwritten for custom payload behavior
    def get_payload(self):
        midnight_local = pd.Timestamp("today").normalize()
        # now get look_back_duration prior
        time_prior = midnight_local - pd.Timedelta(self.look_back_duration)
        payload = {
            "query_start": time_prior.isoformat(),
            "query_end": midnight_local.isoformat()
        }
        return payload

    def dump_data(self):
        payload = self.get_payload()
        return requests.post(f'{self.db_url}/{self.dump_route}', json=payload)

    # by default get filepaths to upload from route response
    def check(self):
        res = self.dump_data()
        data = res.json()
        if 'filepaths' in data:
            # first replace db path with actual path
            filepaths = [filepath.replace(self.container_path, self.actual_path) for filepath in data['filepaths']]
            return {'to do': filepaths, 'failure': []}
        else:
            return {'to do': [], 'failure': []}