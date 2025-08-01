import copy
import re
import json
from pathlib import Path
from datetime import datetime

from source.uploaders.base import BaseUploader

class JSONDocInjectorUploader(BaseUploader):
    """

    This uploader that data is structured as json "documents" (aka payloads) that should be grouped together
    in JSON files. Each payload is uniquely identified by a "document ID" specified at the key value specified in
    "doc_id_key".

    The relative path to the destination JSON file is determined from the payload
        Absolute path should be target path + relative path.
    If the destination file for a new document does not exist it should be created.
    If the destination exists, but it does not contain an entry with the document ID, the payload should be appended
    If the destination exists, but it contains an entry with the document ID, the document should be updated.

    """

    #: Path key to the unique identifier of this payload
    doc_id_key = ""

    #: Regex describing how to extract metadata from the source file path. Must include named groups
    source_regex = ""

    #:
    new_format = ""

    def load_source(self, source_path):
        """

        :param source_path:
        :return:
        """
        with open(source_path, "r") as source_file:
            payload = json.load(source_file)

        if self.source_regex is None:
            meta = {}
        else:
            search = re.search(self.source_regex, self.raw_relative_filepath(source_path))
            meta = search.groupdict()
        return payload, meta


    def make_target_path(self, payload, **kwargs):
        """
        Fill in the given path format spec to create the new target path.
        The context available to format() is all the variables in the payload and extracted metadata combined
        :return: Path, relative path to the JSON file where to inject the current document payload
        """
        context = copy.deepcopy(payload)
        context.update(kwargs)

        path = self.new_format.format(**context)
        return Path(path)

    def inject_payload(self, target_file, payload):
        """
        :param target_file:
        :param payload:
        :return:
        """

        # If any data already exists, load it first as a reference
        if Path(target_file).exists():
            with open(target_file) as json_file:
                contents = json.load(json_file)
        else:
            contents = []

        payload_id = payload[self.doc_id_key]

        # Determine if this payload needs to be appended or replace an existing payload
        placement_loc = None
        for idx, doc in enumerate(contents):
            this_id = doc[self.doc_id_key]
            if payload_id == this_id:
                placement_loc = idx
                break

        # Insert this payload into the appropriate location into the file contents
        if placement_loc is None:
            contents.append(payload)
        else:
            contents[placement_loc] = payload

        # Write the updated file contents to the file
        with open(target_file, 'w') as json_file:
            json_file.write(contents)

    def upload(self, ready):

        successes = []
        errors = []

        for filename in ready:

            destination = "Was not able to determine!"
            try:
                payload, path_meta = self.load_source(filename)
                destination = self.make_target_path(payload, **path_meta)
                self.inject_payload(destination, payload)
            except Exception as e:
                import sys, traceback
                error_dict = {
                    "type": "upload failure",
                    "filename": filename,
                    "destination": destination,
                    "error": str(e),
                    "trace": traceback.format_exception(*sys.exc_info()),
                    "timestamp": datetime.now().timestamp()
                }
                errors.append(error_dict)
                self.warning(
                    f"An upload failed! \n {json.dumps(error_dict, skipkeys=True, indent=2)}"
                )
            else:
                successes.append({
                    "type": "upload success",
                    "filename": filename,
                    "destination": destination,
                    "timestamp": datetime.now().timestamp()
                })