import requests
import pandas as pd
from source.checkers.local import FileCheckerMixin

class MySQLContainerCheckerMixin(FileCheckerMixin):
    """Checker to load files pulled from a MySQL container"""
    # the full URL to connect to the database
    db_url = ''

    # the route needed to dump from the database and retrieve filepaths
    dump_route = ''

    # how far back from midnight we should retrieve data from (as pandas timedelta string)
    look_back_duration = '1D'

    # the path that data is dumped to in the container
    container_path = ''

    # the path that data is dumped to on disk (i.e. where is the dump mounted)
    actual_path = ''

    dump_key = ''

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
        headers = {
            "X-Dump-Key": self.dump_key
        }
        return requests.post(f'{self.db_url}/{self.dump_route}', json=payload, headers=headers)

    # by default get filepaths to upload from route response
    def check(self):
        res = self.dump_data()
        data = res.json()
        if res.ok and 'filepaths' in data:
            # first replace db path with actual path
            filepaths = [filepath.replace(self.container_path, self.actual_path) for filepath in data['filepaths']]
            return {'to do': filepaths, 'failure': []}
        elif not res.ok:
            return {'to do': [], 'failure': [{
                'filename': "UNKNOWN", 
                'type': data['detail'], 
                }]}
        else:
            return {'to do': [], 'failure': [{
                'filename': "UNKNOWN",
                'type': 'unknown server error'
                }]}