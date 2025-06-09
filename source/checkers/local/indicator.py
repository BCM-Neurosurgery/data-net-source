import os
import re
import toml
import copy
from abc import ABC, abstractmethod

from source.common import EMPTY_LOG
from source.checkers.local import FileCheckerMixin


class BaseIndicatorChecker(FileCheckerMixin, ABC):
    """"""

    @abstractmethod
    def parse_indicators(self):
        """Implement this to determine which sub-directories in the source directory to include in the check"""
        pass


    def check(self):
        """Recursively check the contents of a subset of the directories in the given path"""

        to_check = self.parse_indicators()
        to_do = []
        failure = []

        for directory in to_check:
            try:
                found_here = super(BaseIndicatorChecker, self).search_file_tree(source_dir=directory, level=1)
            except FileNotFoundError as e:
                raise FileNotFoundError(f'Indicator file suggested an invalid path: \n  {e.filename}')
            to_do.extend(found_here['to do'])
            failure.extend(found_here['failure'])

        return {'to do': to_do, 'failure': failure}

    def clean_old_indicators(self, saved_state):
        """Remove events related to indicator files/entries that no longer exist"""
        indicated = self.parse_indicators()

        relevant_events = copy.deepcopy(EMPTY_LOG)
        for category, logged_events in saved_state.items():
            for event in logged_events:
                for indication in indicated:
                    if indication in event['uploaded']:
                        relevant_events[category].append()
                    else:
                        self.debug(f'Dropping non-indicated event: {event["uploaded"]}')
        return relevant_events

    def clean(self):
        """Delete local copies of files that have already been uploaded"""
        upload_log = self.load_state()

        # Standard steps for cleaning up the upload state
        most_recent = self.clean_outdated(upload_log)
        trimmed = self.clean_old_success(most_recent)

        # Only save the events related to files that are still indicated
        still_relevant = self.clean_old_indicators(trimmed)

        self.save_state(**still_relevant)

class IndicatorTomlChecker(BaseIndicatorChecker):
    """"""
    source_location = {
        "path": "",
        "indicator_toml": ""
    }

    def parse_indicators(self):

        with open(self.source_location['indicator_toml'], 'r') as f:
            config = toml.load(f)

        check_locations = []
        for patient_id, indicated in config.items():
            sub_path = indicated['path']
            check_locations.append(os.path.join(self.source_location['path'], sub_path))

        return check_locations


class IndicatorFileCheckerMixin(BaseIndicatorChecker):
    """
    Checker that uses a set of indicator files to limit the directories to search for new files

    This can be very useful if you have many small patient directories that should not be deleted, but the majority
    of them will not be updated. By default, all files in the directory which contain only letters or numbers (ie a
    patient ID) as well as an optional file extension will be matched. Everything before the file extension will be
    considered the name of a directory inside the "path" directory to check for new files. For example:
    If the indicator directory contains the files:
        - P01.txt
        - P02
        - P32_ignore.txt
    Then the Checker will look for new files in:
        - <path>/PO1/
        - <path>/PO2/
    All other directories and loose files in the <path> directory will be ignored

    Requires a source config of the following format
    {
        "path": "/path/to/directory/with/data",
        "indicator_dir": "/path/to/directory/with/indicator_files"
    }
    The fields in this source:
      - "indicator_dir": absolute path of the directory where the indicator files are found

    Additional settings
      - indicator_regex: regular expression that defines how the indicator files should be interpreted, must contain
        exactly at least one capturing group, and match the part string only once. This regex will be applied to all the
        files in the indicator_dir directory.
      - indicator_format: The results (capturing groups) of the regex match will be formatted using this format string.
        The result will then be appended to the "path" setting to define the directories that will be searched for new
        files.

    """

    source_location = {
        "path": "",
        "indicator_dir": ""
    }

    indicator_regex = "([a-zA-Z0-9]+)[.a-zA-Z0-9]*"
    indicator_format = "{}"

    def parse_indicators(self):

        indicators = os.listdir(self.source_location['indicator_dir'])
        check_locations = []

        for indicator in indicators:
            result = re.search(self.indicator_regex, indicator)
            if result is None:
                continue  # This file does not match the indicator regex
            else:
                formatted = self.indicator_format.format(*result.groups())
                check_locations.append(os.path.join(self.source_location['path'], formatted))

        return check_locations


