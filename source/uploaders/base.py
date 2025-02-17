import os
import re
import json
from datetime import datetime
from pathlib import Path
from abc import abstractmethod, ABC

import numpy as np


class BaseUploader(ABC):

    @property
    @abstractmethod
    def uploader_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseUploader"

    def relative_filepath(self, filename):
        return os.path.relpath(filename, self.middle_location['path'])

    def remote_filepath(self, filename):
        return os.path.join(self.target_location['path'], self.relative_filepath(filename))

    def remote_dirpath(self, filename):
        return os.path.dirname(self.remote_filepath(filename))

    @abstractmethod
    def upload(self, ready):
        """
        Send data to the data lake, implementation dependent on source and destination

        :param ready: dict with a list of objects to upload and a list of known failures
            Should be of the form {'to upload': [], 'failure': []}
        :returns: a dict describing successful uploads and failures
        """
        return {'success': [], 'failure': []}

    @staticmethod
    def time_upload(upload_size, upload_func, filename, *args, **kwargs):
        """
        Simple wrapper function to get the upload rate for a file

        :param upload_size: size, in MB, of the data to upload
        :param upload_func: function responsible for performing the file upload.
            This function must take a filename as the first argument, all returned values ignored
        :param filename: full path to the file on the local system, used to determine the file size
        :param args: any arguments that need to be passed to the uploader function
        :param kwargs: any keyword arguments that need to be passed to the uploader function
        """
        transfer_start = datetime.now()
        upload_func(filename, *args, **kwargs)
        transfer_end = datetime.now()
        duration = (transfer_end - transfer_start).total_seconds()
        if duration > 0:
            rate = upload_size / duration
        else:
            rate = np.nan
        return rate

    def append_metadata(self, file_list):
        """
        Ensure that metadata about this SourceParser is added to the upload task list

        This function looks for a metadata.json file in the list of files to upload. If no such file is found, make it
        and insert the metadata for this Parser. Otherwise, either add a 'parser' field to the metadata file, and add
        the Parser metadata there, or extend the 'parser' field to be a list in the case that there are multiple
        SourceParsers involved in the ingestion of this data.

        :param file_list:
        """
        meta_files = [file_name for file_name in file_list if file_name.endswith('metadata.json')]
        if meta_files:
            with open(meta_files[0]) as meta_file:
                metadata = json.load(meta_file)
        else:
            metadata = {}

        parser_meta = self.describe_parser()  # Defined in ParserCommon
        if 'parser' not in metadata:
            metadata['parser'] = [parser_meta]
        elif metadata['parser']:
            metadata['parser'].append(parser_meta)

        if meta_files:
            meta_out = meta_files[0]
        else:
            meta_out = 'metadata.json'

        with open(meta_out, 'w') as meta_file:
            json.dump(metadata, meta_file)

    def rebuild_filepath(self, old_file_path):
        """
        Restructure the path of a file before upload

        For this to work the target location config must have an element named 'rebuild_filepath' of the form:
        {
            'source_regex': 'string',
            'path_elements': ['string', ...]
            'new_format': 'string'
        }
        source_regex: This must be a regex pattern that matches the source filepath. It should contain capturing groups
            for all the path elements that should be included in the output filepath. The filepath here will always
            appear as the string representation of a UNIX-style path
        path_elements: list of strings, the names of the path element in each capturing group in the order that they
            appear in the regex/source filepath.
        new_path: the new output path as a python f-string, where the variable names in `{}` correspond to the path
            element names listed in path_elements

        Example:
            old_path: '/source/patientDATAFILE/modality/date.json'
            source_regex: '.*/([a-zA-Z]*)DATAFILE/([a-zA-Z]*)/([0-9-]*).json'
            path_elements: ['patient', 'modality', 'date']
            new_format: 'output/{patient}/{date}/{modality}.json'

        :param old_file_path:
        :return: Path representing the new file name and destination
        """

        # First check if there is any path rebuild information supplied
        if 'rebuild_filepath' not in self.target_location:
            return old_file_path

        rebuild_info = self.target_location['rebuild_filepath']

        old_path_unix = Path(old_file_path).as_posix()
        old_re = rebuild_info['source_regex']

        old_match = re.search(old_re, old_path_unix)
        if old_match is None:
            self.error('Given path regex did not match the source path!')
            raise ValueError('Given path regex did not match the source')

        old_elements = {name: old_match.group(i+1) for i, name in enumerate(rebuild_info['path_elements'])}
        new_path = rebuild_info['new_format'].format(**old_elements)

        return Path(new_path)