import os
import re
import sys
import json
import traceback
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

    def raw_relative_filepath(self, filename):
        """Return the path to this file, relative to its parent source/staging directory"""
        return os.path.relpath(filename, self.middle_location['path'])

    @abstractmethod
    def upload(self, ready):
        """
        Send data to the data lake, implementation dependent on source and destination

        :param ready: dict with a list of objects to upload and a list of known failures
            Should be of the form {'to upload': [], 'failure': []}
        :returns: a dict describing successful uploads and failures
        """
        return {'success': [], 'failure': []}

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


class FileSystemUploader(BaseUploader, ABC):
    """
    Parent class for all uploaders that are transferring files to a filesystem

    This class implements a generic upload function. Subclasses should instead implement the following upload steps:
        - check_exists: check whether this file already exists in the destination filesystem
        - make_folders: make sure that all parent directories exist in the destination filesystem
        - do_move: actually move the file to the destination filesystem.

    When implementing these functions, it is advisable to not explicitly manipulate the file paths, but instead make use
    of three existing functions:
        self.ready_relative_filepath(filename)
        self.destination_filepath(filename)
        self.destination_dirpath(filename)
    See each function's docstring for more information
    """

    @abstractmethod
    def check_exists(self, target_file):
        """
        Return True if this file already exists in the destination filesystem

        :param target_file: absolute path in the destination filesystem of where the file should be stored
        :returns: True if this file already exists in the destination filesystem
        """

    @abstractmethod
    def make_folders(self, target_directory):
        """
        Ensure that the target directory exists

        :param target_directory: absolute path to the directory on the destination filesystem where the current file
            should be stored
        """

    @abstractmethod
    def do_move(self, filename, destination):
        """
        Copy the source file to the target filesystem at destination

        It may be convenient for this function to be a wrapper for time_upload, to collect information about how
        long each file upload took and at what rate the transfer was performed.

        :param filename: absolute path in the source (aka local) filesystem of where the file should be stored
        :param destination: absolute path in the destination filesystem of where the file should be stored
        :returns: (optional) tuple of the file size in MB and transfer rate in MB/s
        """

    def ready_relative_filepath(self, filename):
        """Return the final path to this file, relative to the source directory and rebuilt as needed"""
        return self.rebuild_filepath(self.raw_relative_filepath(filename))

    def destination_filepath(self, filename):
        """Return the absolute path to the file in the planned destination location"""
        return Path(self.target_location['path']) / self.ready_relative_filepath(filename)

    def destination_dirpath(self, filename):
        """Return the deepest level directory of the file in the planned destination location"""
        return self.destination_filepath(filename).parent

    @staticmethod
    def time_upload(upload_func, filename, *args, **kwargs):
        """
        Simple wrapper function to get the upload rate for a file

        :param upload_func: function responsible for performing the file upload.
            This function must take a filename as the first argument, all returned values ignored
        :param filename: full path to the file on the local system, used to determine the file size
        :param args: any arguments that need to be passed to the uploader function
        :param kwargs: any keyword arguments that need to be passed to the uploader function
        """
        upload_size = os.path.getsize(filename) / 1024 ** 2
        transfer_start = datetime.now()
        upload_func(filename, *args, **kwargs)
        transfer_end = datetime.now()
        duration = (transfer_end - transfer_start).total_seconds()
        if duration > 0:
            rate = upload_size / duration
        else:
            rate = np.nan
        return upload_size, rate

    def upload(self, ready):
        """
        This function is responsible for the entire process of transferring files to the destination filesystem
        FileSystemUploader subclasses should not override this function in general but instead implement the individual
        steps of the upload process. See the docstrings on the stub definition of each for more details
            - check_exists: check whether this file already exists in the destination filesystem
            - make_folders: make sure that all parent directories exist in the destination filesystem
            - do_move: actually move the file to the destination filesystem.
        Note that check_exists will only be called if 'allow-overwrite' is False (default behaviour).

        :param ready: dict with a list of filepaths to upload and a list of dicts describing failures
        :return: dict with a list of dicts describing successful uploads and a list of dicts describing failures
        """

        errors = ready["failure"]
        successes = []
        all_rates = []

        for filename in ready["to upload"]:
            destination = "Failed to determine!"
            try:
                # Make sure we want to perform the copy
                target_file = self.destination_filepath(filename)
                if 'allow-overwrite' in self.target_location and not self.target_location['allow-overwrite']:
                    if self.check_exists(target_file):
                        raise FileExistsError(f"{filename} already exists!")

                # Make sure the destination folder exists
                folder_path = self.destination_dirpath(filename)
                self.make_folders(folder_path)

                # Perform the file copy
                destination = self.destination_filepath(filename)
                self.info(f"Copying to {destination}")
                timing_info = self.do_move(filename, destination)
                if timing_info:
                    self.debug(f"  Done. ({timing_info[0]:.2f} MB at {timing_info[1]:.2f} MB/s)")
                else:
                    self.debug(f"  Done.")

            except Exception as e:
                error_dict = {
                    "type": "upload failure",
                    "filename": filename,
                    "destination": destination,
                    "error": str(e),
                    "trace": traceback.format_exception(*sys.exc_info()),
                }
                errors.append(error_dict)
                self.warning(
                    f"An upload failed! \n {json.dumps(error_dict, skipkeys=True, indent=2)}"
                )
            else:
                successes.append(
                    {
                        "type": "upload success",
                        "filename": filename,
                        "destination": destination,
                    }
                )

        if len(all_rates):
            self.debug(f"Average transfer rate {round(np.nanmean(all_rates), 2)} MB/s")
        else:
            self.info(f"No files transferred.")
        return {"success": successes, "failure": errors}

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


class RemoteFilesystemUploader(FileSystemUploader, ABC):
    """
    Parent class for uploading files to a remote filesystem.
    Requires an additional 'make_connection' method
    """

    @abstractmethod
    def make_connection(self):
        """
        Establish a connection to the remote filesystem
        Connection reference should be stored as instance variables
        """

    @abstractmethod
    def close_connection(self):
        """"""

    def upload(self, ready):
        """Wrapper around the generic filesystem upload function that additionally makes and closes a connection"""
        self.make_connection()
        try:
            super().upload(ready)
        finally:
            self.close_connection()
