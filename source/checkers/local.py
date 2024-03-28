import json
import os
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
        source_dir = self.source_location  # Defined in ParserBase
        dirs_here = [
            directory for directory in os.listdir(source_dir)
            if os.path.isdir(os.path.join(source_dir, directory))
        ]

        # TODO: the log will need to be parsed somehow, not sure what other info we will save here
        successes = self.load_success_log()
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

    checker_name = "FileChecker"

    def check(self, source_dir=None):
        """Check only the individual files in a directory if they have been uploaded or not"""

        # Draw the source location from the class settings if not passed explicitly under recursion
        source_dir = self.source_location if source_dir is None else source_dir

        successes = self.load_success_log()
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
                check_inside = self.check(full_path)
                to_upload.extend(check_inside['to do'])

        return {'to do': to_upload, 'failure': []}

    def build_log_entry(self, entry_data):
        return {
            'type': 'file',
            'checked': self.source_location,
            'uploaded': entry_data['filename'],
            'status': entry_data['type'],
            'parser': self.describe_parser(),
            'timestamp': datetime.now().timestamp()
        }

    def save(self, completed):
        """Log the files the that have been uploaded, along with all errors"""
        # TODO: make this work with the method of passing around dicts
        logged_data = self.load_log()

        new_success = [self.build_log_entry(success) for success in completed['success']]
        logged_data['success'].extend(new_success)

        new_failure = [self.build_log_entry(failure) for failure in completed['failure']]
        logged_data['failure'].extend(new_failure)

        with open(os.path.join(self.middle_location, self.log_filename), 'w') as log:
            json.dump(logged_data, log, indent=2)

    def clean(self):
        """Delete local copies of files that have already been uploaded"""
        upload_log = self.load_log()

        successes = upload_log['success']
        errors = upload_log['failure']

        # Remove errors that were later replaced by successes
        unfixed_failures = []
        for error in errors:
            for success in successes:
                if success['uploaded'] == error['uploaded'] and success['timestamp'] > error['timestamp']:
                    self.info(f'File was uploaded later successfully {error["uploaded"]}')
                    break
            else:
                self.info(f'File never uploaded {error["uploaded"]}')
                unfixed_failures.append(error)

        # Remove all but the most recent error for every file
        most_recent_errors = []
        checked_files = []
        for error in unfixed_failures:
            if error['uploaded'] in checked_files:
                pass  # The most recent error for this file was already selected
            else:
                # Get and save only the most recent error out of all errors for this file
                all_matching = [err for err in unfixed_failures if err['uploaded'] == error['uploaded']]
                youngest = error
                for match in all_matching:
                    if match['timestamp'] < youngest['timestamp']:
                        youngest = match
                if len(all_matching) > 1:
                    self.info(f'Trimmed {len(all_matching)-1} errors for {error["uploaded"]}')
                most_recent_errors.append(youngest)

                # We won't check errors for this file again
                checked_files.append(error['uploaded'])

        # Delete files that have been successfully uploaded long enough ago
        kept_success = []
        now = datetime.now().timestamp()
        for uploaded in successes:
            age = uploaded['timestamp'] - now
            if age > self.delete_age:
                self.info(f'Deleting {uploaded["uploaded"]}')
                try:
                    os.remove(uploaded['uploaded'])
                except FileNotFoundError:
                    self.warning(f'File was already deleted!')
            else:
                kept_success.append(uploaded)


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

    def check(self, source_dir=None):
        """
        Same as in the FileCheckerMixin, but additionally ensure that they have finished being written

        Essentially, we do not want to upload files while data is still being written to them. This is useful for
        situations where data is streamed directly to chunked files, and we want to start gathering data before the
        data stream is complete. To do this, we need to know approx how often the file is written to, and only include
        files that haven't been written to in at least that long
        """

        all_new_files = super(StreamedFileCheckerMixin, self).check(source_dir=source_dir)
        min_time_unmodified = self.stream_rate * self.reliability_factor

        to_upload = []
        failure = all_new_files['failure']
        for filepath in all_new_files['to do']:

            # Streamed files should only be included if they're old enough
            if self.is_streamed_file(filepath):
                last_modified = os.path.getmtime(filepath)
                secs_since_mod = datetime.now().timestamp() - last_modified
                if secs_since_mod > min_time_unmodified:
                    to_upload.append(filepath)
                else:
                    self.info(f'You need to be at least {round(min_time_unmodified, 2) } seconds old ride this ride!\n'
                              f'  This file was only {round(secs_since_mod, 2)} seconds old\n'
                              f'  Skipped: {filepath}')

            # Init files can be written right away
            elif self.is_init_file(filepath):
                to_upload.append(filepath)

        return {'to do': to_upload, 'failure': failure}
