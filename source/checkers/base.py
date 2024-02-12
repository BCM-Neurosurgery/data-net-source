import os
import json
from abc import ABC, abstractmethod


class BaseChecker(ABC):
    """Base class for all checkers that defines the interface"""
    log_filename = 'upload_log.json'

    def load_log(self):
        with open(os.path.join(self.middle_location, self.log_filename)) as f:
            log = json.load(f)
        return log

    def load_success_log(self):
        uploaded = self.load_log()['success']
        return uploaded

    def write_log(self, log_data):
        with open(os.path.join(self.middle_location, self.log_filename), 'w') as log:
            json.dump(log_data, log, indent=2)

    @property
    @abstractmethod
    def checker_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseChecker"

    @abstractmethod
    def check(self):
        """
        Find new data that is ready to be parsed

        :returns: a dict describing new data and failures
        """
        return {'to do': [], 'failure': []}

    @abstractmethod
    def save(self, completed):
        """"""

