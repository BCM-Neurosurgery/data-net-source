import json
import os
import shutil
import sys
import traceback
import pathlib
import numpy as np
from source.uploaders.base import BaseUploader, FileSystemUploader


class BucketUploaderMixin(FileSystemUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """

    uploader_name = "BucketUploaderMixin"


class CopyUploaderMixin(FileSystemUploader):
    """
    Simple uploader that uses shutil to copy files from one local directory to another

    Middle Format:
    {
      "path": ""  # Path to the parent directory where the files to copy over are stored
    }

    Target Format:
    {
      "path": ""  # Path to the parent directory where the files to copy over are stored
    }

    Note: even though full file paths for all the files are passed to the upload function through the to_do dict,
    the parent paths are still necessary to correctly generate the relative file paths and therefore the correct
    output paths in the target directory.
    """

    uploader_name = "CopyUploaderMixin"
    middle_location = {
        'path': '',
    }
    target_location = {
        'path': ''
    }

    def check_exists(self, target_file):
        """Return True if this file already exists in the destination filesystem"""
        return os.path.exists(target_file)

    def make_folders(self, target_directory):
        """Ensure that the target directory exists"""
        if not os.path.exists(target_directory):
            os.makedirs(target_directory)

    def do_move(self, filename, destination):
        """Copy the source file to the target filesystem at destination"""
        return self.time_upload(shutil.copy, filename, destination)