import os
import json
from abc import ABC, abstractmethod


class BaseChecker(ABC):
    """Base class for all checkers that defines the interface"""
    state_filename = 'upload_state.json'
    state_path = "path/to/state/save/dir"

    def load_state(self):
        """
        Load the saved upload state from a previously saved file

        :return: Dictionary containing the upload state for all data
        The state must always contain two lists: 'success', which lists all data units which were successfully
        processed and uploaded; and 'failure', which lists all data units for which an error occurred somewhere
        in the processing/upload pipeline.
        Each entry for each data unit should be a dictionary which contains all the appropriate information. Required
        keys in each of these are:
          - `timestamp`: the UNIX UTC timestamp at which this state even occurred

        """
        with open(os.path.join(self.state_path, self.state_filename)) as f:
            log = json.load(f)
        return log

    def load_successes(self):
        uploaded = self.load_state()['success']
        return uploaded

    def write_state(self, state_data):
        """
        Write the passed state of successes and failures to file for later reference

        See `load_state()` for details of the required state_data format
        """
        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(state_data, log, indent=2)

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

    @abstractmethod
    def clean(self):
        """
        Ensure the upload state is kept clean

        This function is responsible for ensuring each file appears only once in the upload log, and that old files
        that have already been uploaded are deleted from local storage.
        """
