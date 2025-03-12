import os
from datetime import datetime

from source.checkers.local.base import FileCheckerMixin


class StreamedFileCheckerMixin(FileCheckerMixin):
    """Checker to load files from a directory that is being actively streamed to"""

    #: List of file endings that appear shortly after recording start, and can be uploaded right way
    initialize_files = []

    #: list of file endings that should be considered as streamed files, and should not be uploaded right away
    #: If streamed files is '*' instead of a list, all files will be identified as streamed files
    streamed_files = []

    #: list of file endings that only appear when the recording has ended
    termination_files = []

    #: Time, in seconds, between file updates in the streamed files
    stream_rate = 60

    #: Factor measuring how reliable the update rate is. Will wait this many times the stream_rate before including
    reliability_factor = 1.0

    @staticmethod
    def is_file_category(filename, category_info):
        """
        Check to see if a file belongs to a file category by parsing the category info and comparing it to
        the file type endings (everything after the last period)

        :param filename:
        :param category_info: List of strings, string, or None.  If a list, then each element of the list specifies
        a file time to (for example: txt, csv) to consider as member of this category.
        Besides this case, there are two special cases:
            - string '*': will match all file types
            - None: will match no file types, equivalent to []
        :return:
        """
        # Special behaviors are checked first
        if category_info == '*':
            return True
        elif category_info is None:
            return False

        # Check each file ending in the list
        for ending in category_info:
            if filename.endswith(ending):
                return True

        # We only reach here if none of the file endings matched
        return False

    def is_init_file(self, filename):
        """Check if the given file is an initialization file, that is not streamed"""
        return self.is_file_category(filename, self.initialize_files)

    def is_streamed_file(self, filename):
        """Check if the given file is a streamed file that is written to incrementally"""
        return self.is_file_category(filename, self.streamed_files)

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
