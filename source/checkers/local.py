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
    """
    Mixin to add a checker that recursively searches for new files


    """

    checker_name = "FileChecker"

    def check(self, source_dir=None):
        """Check only the individual files in a directory if they have been uploaded or not"""

        # Draw the source location from the class settings if not passed explicitly under recursion
        source_dir = self.source_location if source_dir is None else source_dir
        log_dir = self.source_location  # Log is always saved at the top level

        successes = load_success_log(os.path.join(log_dir, self.log_filename))
        uploaded_files = [success['uploaded'] for success in successes]

        # Determine which of the files here need to be uploaded
        to_upload = []
        for item_here in os.listdir(source_dir):
            full_path = os.path.join(source_dir, item_here)

            # Skip any files and folders that have already been logged as complete
            if full_path in uploaded_files:
                continue

            # For any files besides the logfile check if they've been uploaded
            if os.path.isfile(full_path) and item_here != self.log_filename:
                to_upload.append(full_path)

            # For any directories that have not been marked as completed, process recursively
            elif os.path.isdir(full_path):
                to_upload.extend(self.check(full_path))

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


class StreamedFileChecker(BaseChecker):
    """Checker to load files from a directory that is being actively streamed to"""

    def __init__(self):
        initialize_files = ['*.ccf', '*.csr', '*.sif', '*.toc']
        streamed_files = ['*.nev', '*.ns3', '*.ns5']
        file_duration = None




