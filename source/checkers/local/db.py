import os
from datetime import datetime
import requests
from datetime import datetime, timedelta, time, date
from source.checkers.local import FileCheckerMixin

class DBFileCheckerMixin(FileCheckerMixin):
    db_url = ''
    dump_route = ''
    # look back duration in minutes, default to 24 hours
    look_back_duration = 1440

    # by default gets data from midnight to 'look_back_duration' prior
    # method can be overwritten for custom payload behavior
    def get_payload(self):
        current_date = date.today()
        midnight_local = datetime.combine(current_date, time.min)
        # now get look_back_duration prior
        time_prior = midnight - timedelta(minutes=look_back_duration)
        payload = {
            "query_start": time_prior.isoformat(),
            "query_end": midnight_local.isoformat()
        }
        return payload

    def dump_data(self):
        payload = self.get_payload()
        return res = requests.post(f'{db_url}/{dump_route}', data=payload)

    # by default get filepaths to upload from route response
    def check(self):
        res = self.dump_data()
        data = res.json()
        if 'filepaths' in data:
            return {'to do': data['filepaths'], 'failure': []}
        else:
            return {'to do': [], 'failure': []}