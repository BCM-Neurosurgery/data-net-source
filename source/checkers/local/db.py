import os
from datetime import datetime
import requests

from source.checkers.local import FileCheckerMixin

class DBFileCheckerMixin(FileCheckerMixin):
    db_url = ''
    dump_route = ''

    # by default dumps all data without any filtration - child classes can change this behavior
    def dump_data(self, payload=None):
        return res = requests.post(f"{db_url}/{dump_route}", data=payload)

    # check is same as FileCheckerMixin, but simply dumps data prior to doing file check
    def check(self):
        self.dump_data()
        super().check()