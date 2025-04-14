import os
import json
from datetime import datetime
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
        """
        Load and return only the `success` part of the upload state
        """
        uploaded = self.load_state()['success']
        return uploaded

    def load_skipped(self):
        """Load all tasks that were skipped during the upload process"""
        return self.load_state()['skipped']

    def load_non_failure(self):
        """Load the list of all tasks that did not result in a failure"""
        return self.load_successes() + self.load_skipped()

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
        There are several commonly used actions implemented that you can call if it makes sense for your parser
        """

    def clean_fixed_failures(self, successes, failures):
        """Remove failures in the upload state that were later replaced by successes"""
        unfixed_failures = []
        for failure in failures:
            for success in successes:
                if success['uploaded'] == failure['uploaded'] and success['timestamp'] > failure['timestamp']:
                    self.info(f'File was uploaded later successfully {failure["uploaded"]}')
                    break
            else:
                self.info(f'File never uploaded {failure["uploaded"]}')
                unfixed_failures.append(failure)
        return unfixed_failures

    def clean_duplicate_failures(self, failures):
        """Remove all but the most recent error for every file"""
        most_recent_errors = []
        checked_files = []
        for error in failures:
            if error['uploaded'] in checked_files:
                pass  # The most recent error for this file was already selected
            else:
                # Get and save only the most recent error out of all errors for this file
                all_matching = [err for err in failures if err['uploaded'] == error['uploaded']]
                youngest = error
                for match in all_matching:
                    if match['timestamp'] < youngest['timestamp']:
                        youngest = match
                if len(all_matching) > 1:
                    self.info(f'Trimmed {len(all_matching) - 1} errors for {error["uploaded"]}')
                most_recent_errors.append(youngest)

                # We won't check errors for this file again
                checked_files.append(error['uploaded'])
        return most_recent_errors

    def clean_old_success(self, successes):
        """Delete files that have been successfully uploaded long enough ago"""
        kept_success = []
        now = datetime.now().timestamp()
        has_delete = hasattr(self, 'delete_age_hours')
        for uploaded in successes:
            age = (now - uploaded['timestamp']) / (60 * 60)  # Time since upload in hours
            if has_delete and age > self.delete_age_hours >= 0:
                self.info(f'Deleting {uploaded["uploaded"]}')
                try:
                    os.remove(uploaded['uploaded'])
                except FileNotFoundError:
                    self.warning(f'File was already deleted!')
            else:
                kept_success.append(uploaded)
        return kept_success