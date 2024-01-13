import json
import os
from datetime import datetime

from source.checkers.base import BaseChecker, load_success_log


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
        source_dir = self.source_location  # Defined in ParserBase
        dirs_here = [
            directory for directory in os.listdir(source_dir)
            if os.path.isdir(os.path.join(source_dir, directory))
        ]

        # TODO: the log will need to be parsed somehow, not sure what other info we will save here
        successes = load_success_log(os.path.join(source_dir, self.log_filename))
        already_uploaded = [os.path.join(obj['checked'], obj['uploaded']) for obj in successes]

        to_upload = [
            directory for directory in dirs_here
            if directory not in already_uploaded
        ]
        return to_upload

    def save(self, completed):
        # TODO: Implement a save
        pass


class FileCheckerMixin(BaseChecker):

    checker_name = "FileChecker"

    def check(self):
        """Check only the individual files in a directory if they have been uploaded or not"""
        source_dir = self.source_location  # Defined in ParserBase
        files_here = [
            filename for filename in os.listdir(source_dir)
            if os.path.isfile(os.path.join(source_dir, filename) and filename != self.log_filename)
        ]

        successes = load_success_log(os.path.join(source_dir, self.log_filename))
        uploaded_files = [success['uploaded'] for success in successes]

        to_upload = [
            filename for filename in files_here
            if filename not in uploaded_files
        ]
        return to_upload

    def build_log_entry(self, entry_data):
        return {
            'type': 'file',
            'checked': self.source_location,
            'uploaded': entry_data['filename'],
            'status': entry_data['status'],
            'parser': self.describe_parser(),
            'timestamp': datetime.now().timestamp()
        }

    def save(self, completed):
        """Log the files the that have been uploaded, along with all errors"""
        logged_data = self.load_log()

        new_success = [self.build_log_entry(success) for success in completed['success']]
        logged_data['success'].extend(new_success)

        new_failure = [self.build_log_entry(failure) for failure in completed['failure']]
        logged_data['failure'].extend(new_failure)

        with open(os.path.join(self.source_location, self.log_filename), 'w') as log:
            json.dump(logged_data, log, indent=2)
