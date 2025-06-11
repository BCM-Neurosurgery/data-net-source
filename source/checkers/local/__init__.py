import os
import re
import json
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

    def clean(self):
        # TODO: Implement cleanup
        pass


class FileCheckerMixin(BaseChecker):
    """
    This Checker mix-in class provides functionalities to check for files in a file tree, often used as a base class for
    more purpose-specific Checker classes. Implements commonly used functionality such as recursive directory traversal,
    regex-based filtering, and logging of successful and failed uploads.

    :ivar verbose_level: Controls the verbosity of the output during recursive file searches. Specifically, determines
        how many levels of directories will be printed during the recursive search.
    :type verbose_level: int
    :ivar checker_name: Name of the checker mixin. Used to identify the checker in the upload log.
    :type checker_name: str
    :ivar delete_age_hours: (default -1) Time in hours to retain local copies of files post-upload before deletion. The
        default value of -1 disables deletion of local copies.
    :type delete_age_hours: int
    """
    verbose_level = 2
    checker_name = "FileChecker"

    #: Time to wait after upload before deleting the source version of a file
    delete_age_hours = -1  # Do not delete ever by default

    def check(self):
        """Recursively search the entire file tree for un-uploaded files"""
        return self.search_file_tree()

    def check_regex(self, full_path, pattern_key, default=False):
        """
        Check the filepath against a regex pattern in the source settings

        :param full_path: full absolute path to the file
        :param pattern_key: keyname of the regex pattern to use in the parser.init.source settings table
        :param default: default boolean result to use if the key is not in the settings
        :return: boolean, whether the regex matched
        """
        if pattern_key in self.source_location:
            search = re.search(self.source_location[pattern_key], full_path)
            return search is not None   # True if our regex matched
        # Never skip files if not filter regex was passed
        else:
            return default

    def check_regex_filter(self, full_path):
        """Check a filepath against the filter regex, returning True if a file should be uploaded"""
        return self.check_regex(full_path, pattern_key='regex_filter', default=True)

    def check_regex_exclude(self, full_path):
        """Check a filepath against the filter regex, returning True if a file should be skipped"""
        return self.check_regex(full_path, pattern_key='regex_exclude', default=False)

    def search_file_tree(self, source_dir=None, level=0):
        """
        Recursively searches through a file tree starting at the specified directory and
        determines which files need to be uploaded. The method considers previously logged
        successes, applies inclusion and exclusion filters, and processes nested directories if needed.

        :param source_dir: The directory from which to start the search. Must be provided via the config file
        :type source_dir: str
        :param level: The depth level of recursion. Defaults to 0, only used to track depth for verbose output.
        :type level: int
        :return: A dictionary containing two keys:
                 - 'to do': A list of files to be uploaded.
                 - 'failure': list of directories that could not be processed due to an error.
        :rtype: dict
        """
        # Draw the source location from the class settings if not passed explicitly under recursion
        source_dir = self.source_location['path'] if source_dir is None else source_dir

        successes = self.load_non_failure()
        uploaded_files = [success['uploaded'] for success in successes]

        # Determine which of the files here need to be uploaded
        to_upload = []
        failures = []
        for item_here in os.listdir(source_dir):
            full_path = os.path.join(source_dir, item_here)

            # Skip any files and folders that have already been logged as complete
            if full_path in uploaded_files:
                continue

            # Explicitly check all the files against the optional regex and that they are not the state file
            if os.path.isfile(full_path):
                if self.check_regex_filter(full_path) and not self.check_regex_exclude(full_path):
                    to_upload.append(full_path)

            # For any directories that have not been marked as completed, process recursively
            elif os.path.isdir(full_path):
                try:
                    check_inside = self.search_file_tree(full_path, level=level + 1)
                except Exception as e:
                    failures.append({
                        'type': 'file',
                        'checked': full_path,
                        'status': 'checker error',
                        'error': f'{e}',
                        'timestamp': datetime.now().timestamp()
                    })
                to_upload.extend(check_inside['to do'])

        if level and level < self.verbose_level:
            self.info(f'Checked everything in {source_dir}')
        return {'to do': to_upload, 'failure': failures}

    def build_log_entry(self, entry_data):
        log_entry = {
            'type': 'file',
            'checked': self.source_location['path'],
            'uploaded': entry_data['filename'],
            'status': entry_data['type'],
            'parser': self.describe_parser(),
            'timestamp': datetime.now().timestamp()
        }
        return log_entry

    def save_state(self, success=None, failure=None, skipped=None):
        """Write the upload state json file which records the current state of all uploads"""
        new_log = {'success': success, 'failure': failure, 'skipped': skipped}
        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(new_log, log, indent=2)

        cat_lengths = [f'{len(events)} {cat} events' for cat, events in new_log.items()]
        self.info("Saved state file with: " + ", ".join(cat_lengths))

    def save(self, completed):
        """Log the files the that have been uploaded, along with all errors"""
        # TODO: make this work with the method of passing around dicts
        logged_data = self.load_state()

        # Make sure all the completed states will be saved
        for key in completed.keys():
            if key not in logged_data:
                self.warn(f'Saved state was missing key "{key}". Will be added')
                logged_data[key] = []

        # For all logged categories, make sure all the data is neatly formatted
        for category in logged_data.keys():
            cat_data = [self.build_log_entry(event) for event in completed[category]]
            logged_data[category].extend(cat_data)

        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(logged_data, log, indent=2)

    def clean(self):
        """
        Cleans upload logs by removing fixed failures, duplicate failures, and old successes
        from the log data. Updates the state after performing all cleaning operations.

        :raises KeyError: If the required keys ('success', 'failure') are not found in the
            upload log.

        :return: None
        """
        upload_log = self.load_state()

        reduced_log = self.clean_outdated(upload_log)
        kept_success = self.clean_old_success(reduced_log)
        reduced_log['success'] = kept_success['success']

        self.save_state(**reduced_log)
