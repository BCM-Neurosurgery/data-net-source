import os
import json
from datetime import datetime
from abc import abstractmethod, ABC


class BaseUploader(ABC):

    @property
    @abstractmethod
    def uploader_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseUploader"

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
        rate = size / duration
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


