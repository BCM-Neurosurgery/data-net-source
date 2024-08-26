import json
import os
import re
import shutil
from datetime import datetime

from source.checkers.base import BaseChecker


class DirectoryCheckerMixin(BaseChecker):
    """
    Mixin to a parser that checks whether an entire directory has already been uploaded or not
    """
    checker_name = "DirectoryChecker"

    def check(self):
        """
        Compare the files in a directory to find which still need to be uploaded
        :return:
        """
        source_dir = self.source_location['path']  # Defined in ParserBase
        dirs_here = [
            directory for directory in os.listdir(source_dir)
            if os.path.isdir(os.path.join(source_dir, directory))
        ]

        # TODO: the log will need to be parsed somehow, not sure what other info we will save here
        successes = self.load_successes()
        already_uploaded = [os.path.join(obj['checked'], obj['uploaded']) for obj in successes]

        to_upload = [
            directory for directory in dirs_here
            if directory not in already_uploaded
        ]
        return {'to do': to_upload, 'failure': []}

    def save(self, completed):
        # TODO: Implement a save
        pass


class FileCheckerMixin(BaseChecker):
    """
    Mixin to add a checker that recursively searches for new files


    """
    verbose_level = 2
    checker_name = "FileChecker"

    #: Time to wait after upload before deleting the source version of a file
    delete_age_hours = -1  # Do not delete ever by default

    def check(self):
        """Recursively search the entire file tree for un-uploaded files"""
        return self.search_file_tree()

    def search_file_tree(self, source_dir=None, level=0):
        """Check only the individual files in a directory if they have been uploaded or not"""

        # Draw the source location from the class settings if not passed explicitly under recursion
        source_dir = self.source_location['path'] if source_dir is None else source_dir

        successes = self.load_successes()
        uploaded_files = [success['uploaded'] for success in successes]

        # Determine which of the files here need to be uploaded
        to_upload = []
        for item_here in os.listdir(source_dir):
            full_path = os.path.join(source_dir, item_here)

            # Skip any files and folders that have already been logged as complete
            if full_path in uploaded_files:
                continue

            # For any files besides the logfile check if they've been uploaded
            if os.path.isfile(full_path) and item_here != self.state_filename:
                to_upload.append(full_path)

            # For any directories that have not been marked as completed, process recursively
            elif os.path.isdir(full_path):
                check_inside = self.search_file_tree(full_path, level=level + 1)
                to_upload.extend(check_inside['to do'])

        if level and level < self.verbose_level:
            self.info(f'Checked everything in {source_dir}')
        return {'to do': to_upload, 'failure': []}

    def build_log_entry(self, entry_data):
        return {
            'type': 'file',
            'checked': self.source_location['path'],
            'uploaded': entry_data['filename'],
            'status': entry_data['type'],
            'parser': self.describe_parser(),
            'timestamp': datetime.now().timestamp()
        }

    def save_state(self, successes, failures):
        """Write the upload state json file which records the current state of all uploads"""
        new_log = {'success': successes, 'failure': failures}
        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(new_log, log, indent=2)

    def save(self, completed):
        """Log the files the that have been uploaded, along with all errors"""
        # TODO: make this work with the method of passing around dicts
        logged_data = self.load_state()

        new_success = [self.build_log_entry(success) for success in completed['success']]
        logged_data['success'].extend(new_success)

        new_failure = [self.build_log_entry(failure) for failure in completed['failure']]
        logged_data['failure'].extend(new_failure)

        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(logged_data, log, indent=2)

    def clean(self):
        """Delete local copies of files that have already been uploaded"""
        upload_log = self.load_state()

        unfixed_failures = self.clean_fixed_failures(upload_log['success'], upload_log['failure'])
        most_recent_fails = self.clean_duplicate_failures(unfixed_failures)
        kept_success = self.clean_old_success(upload_log['success'])
        self.save_state(kept_success, most_recent_fails)


class StreamedFileCheckerMixin(FileCheckerMixin):
    """Checker to load files from a directory that is being actively streamed to"""

    #: List of file endings that appear shortly after recording start, and can be uploaded right way
    initialize_files = []

    #: list of file endings that should be considered as streamed files, and should not be uploaded right away
    streamed_files = []

    #: list of file endings that only appear when the recording has ended
    termination_files = []

    #: Time, in seconds, between file updates in the streamed files
    stream_rate = None

    #: Factor measuring how reliable the update rate is. Will wait this many times the stream_rate before including
    reliability_factor = None

    def is_init_file(self, filename):
        """Check if the given file is an initialization file, that is not streamed"""
        for ending in self.initialize_files:
            if filename.endswith(ending):
                return True
        else:
            return False

    def is_streamed_file(self, filename):
        """Check if the given file is a streamed file that is written to incrementally"""
        for ending in self.streamed_files:
            if filename.endswith(ending):
                return True
        else:
            return False

    def filter_streamed_files(self, file_list):
        """Filter out only the streamed files that are old enough to be processed"""
        min_time_unmodified = self.stream_rate * self.reliability_factor

        matching = []
        for filepath in file_list:

            # Streamed files should only be included if they're old enough
            if self.is_streamed_file(filepath):
                last_modified = os.path.getmtime(filepath)
                secs_since_mod = datetime.now().timestamp() - last_modified
                if secs_since_mod > min_time_unmodified:
                    matching.append(filepath)
                else:
                    self.info(f'You need to be at least {round(min_time_unmodified, 2)} seconds old ride this ride!\n'
                              f'  This file was only {round(secs_since_mod, 2)} seconds old\n'
                              f'  Skipped: {filepath}')

            # Init files can be written right away
            elif self.is_init_file(filepath):
                matching.append(filepath)

        return matching

    def check(self):
        """
        Same as in the FileCheckerMixin, but additionally ensure that they have finished being written

        Essentially, we do not want to upload files while data is still being written to them. This is useful for
        situations where data is streamed directly to chunked files, and we want to start gathering data before the
        data stream is complete. To do this, we need to know approx how often the file is written to, and only include
        files that haven't been written to in at least that long
        """

        all_new_files = super(StreamedFileCheckerMixin, self).search_file_tree()

        to_upload = self.filter_streamed_files(all_new_files['to do'])
        failure = all_new_files['failure']

        return {'to do': to_upload, 'failure': failure}


class IndicatorFileCheckerMixin(FileCheckerMixin):
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

    def check(self):
        """Recursively check the contents of a subset of the directories in the given path"""

        to_check = self.parse_indicators()
        to_do = []
        failure = []

        for directory in to_check:
            try:
                found_here = super(IndicatorFileCheckerMixin, self).search_file_tree(source_dir=directory, level=1)
            except FileNotFoundError as e:
                raise FileNotFoundError(f'Indicator file suggested an invalid path: \n  {e.filename}')
            to_do.extend(found_here['to do'])
            failure.extend(found_here['failure'])

        return {'to do': to_do, 'failure': failure}

    def clean_old_indicators(self, indicated, logged_events):
        """"""
        relevant_events = []
        for event in logged_events:
            for indication in indicated:
                if indication in event['uploaded']:
                    relevant_events.append(event)
                    break  # We can skip to the next event since this one is already saved
        return relevant_events

    def clean(self):
        """Delete local copies of files that have already been uploaded"""
        upload_log = self.load_state()

        # Standard steps for cleaning up the upload state
        unfixed_failures = self.clean_fixed_failures(upload_log['success'], upload_log['failure'])
        most_recent_fails = self.clean_duplicate_failures(unfixed_failures)
        kept_success = self.clean_old_success(upload_log['success'])

        # Only save the events related to files that are still indicated
        check_locations = self.parse_indicators()
        relevant_success = self.clean_old_indicators(check_locations, kept_success)
        relevant_failure = self.clean_old_indicators(check_locations, most_recent_fails)

        self.save_state(relevant_success, relevant_failure)


