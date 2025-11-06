import copy
import os
import json
from datetime import datetime
from abc import ABC, abstractmethod
from typing import List, Dict

from source.common import EMPTY_LOG


class BaseChecker(ABC):
    """Base class for all checkers that defines the interface"""
    state_filename = 'upload_state.json'
    state_path = "path/to/state/save/dir"

    # -------------------------------------------------------------------------
    # --- Abstract properties for metadata (required for config generator) ---
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def checker_name(self) -> str:
        """
        The name of this checker mixin class.
        
        :return: Class name (e.g., 'FileCheckerMixin')
        """
        pass

    @property
    @abstractmethod
    def mixin_module_path(self) -> str:
        """
        The module path where this mixin is defined.
        
        :return: Module path relative to 'source' (e.g., 'checkers.local.__init__')
        """
        pass

    @property
    @abstractmethod
    def mixin_description(self) -> str:
        """
        Human-readable description of what this checker does.
        
        :return: Description string for config generator
        """
        pass

    @property
    @abstractmethod
    def required_dependencies(self) -> List[str]:
        """
        List of Python packages required by this checker.
        
        :return: List of package names (e.g., ['boto3', 'requests'])
        """
        pass

    @property
    @abstractmethod
    def config_with_comments(self) -> Dict[str, tuple]:
        """
        Configuration template with inline comments.
        
        Each key maps to a tuple of (value, comment) where:
        - value: The default/example value for this config field
        - comment: Human-readable description of what the field does
        
        Example:
            {
                'path': ('path/to/directory', 'Directory to check for files'),
                'check_for_modifications': (False, 'Whether to check for modified files')
            }
        
        :return: Dictionary mapping config keys to (value, comment) tuples
        """
        pass

    # -------------------------------------------------------------------------
    # --- Concrete helper methods ---
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # --- Abstract methods to be implemented by concrete checkers ---
    # -------------------------------------------------------------------------

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

    def clean_outdated(self, full_state):
        """Remove all the entries for a particular source file except for the most recent one."""

        def iter_state(key, state_dict):
            for obj in state_dict[key]:
                if 'filename' in obj:
                    yield obj['filename'], obj
                elif 'uploaded' in obj:
                    yield obj['uploaded'], obj

        # Re-organize the state dictionary to be easier to compare age of events per file
        re_organized = {}
        for category in full_state:
            for filename, event in iter_state(category, full_state):
                if filename not in re_organized:
                    re_organized[filename] = []
                re_organized[filename].append((category, event))

        # For each unique filename, save only the most recent event
        reduced = copy.deepcopy(EMPTY_LOG)
        for filename, entries in re_organized.items():
            if len(entries) > 1:    # If there are multiple entries sort them in time
                entries = sorted(entries, key=lambda x: x[1]['timestamp'])
                self.info(f'Saving only "{entries[-1][0]}" for {filename} (will drop {len(entries) - 1} entries)')
                for to_drop in entries[:-1]:
                    timestamp = datetime.fromtimestamp(to_drop[1]['timestamp'])
                    elapsed = (datetime.now() - timestamp).total_seconds() / 3600
                    self.debug(f'  Dropping {to_drop[0]} at {timestamp} ({elapsed:.1f} hours ago)')
            cat, event = entries[-1]
            reduced[cat].append(event)

        return reduced

    def clean_old_success(self, state):
        """Delete files that have been successfully uploaded long enough ago"""
        successes = state['success']
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

        # Keep all non-success entries the same
        new_log = copy.deepcopy(state)
        new_log['success'] = kept_success

        return new_log