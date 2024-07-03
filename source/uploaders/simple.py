import json
import os
import shutil
import sys
import traceback
import pathlib
import numpy as np
from source.uploaders.base import BaseUploader


class BucketUploaderMixin(BaseUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """

    uploader_name = "BucketUploaderMixin"

    def upload(self, ready):
        raise NotImplementedError


class CopyUploaderMixin(BaseUploader):
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

    def upload(self, ready):

        errors = ready["failure"]
        successes = []
        all_rates = []

        for filename in ready["to upload"]:
            destination = "Failed to determine!"
            try:
                rel_filepath = os.path.relpath(
                    filename, start=self.middle_location["path"]
                )

                # Make sure the destination folder exists
                new_rel_path = self.rebuild_filepath(rel_filepath)
                folder_path = os.path.join(
                    self.target_location["path"], os.path.dirname(new_rel_path)
                )
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                # Perform the file copy
                destination = os.path.join(self.target_location["path"], new_rel_path)
                self.info(
                    f"Copying to {destination}",
                )
                size = os.path.getsize(filename) / 1024**2  # File size in MB
                rate = self.time_upload(size, shutil.copy, filename, destination)
                self.info(
                    f"  Done. ({np.round(size, 2)} MB at {np.round(rate, 2)} MB/s)"
                )

                if size > 1.0:
                    all_rates.append(rate)

            except Exception as e:
                error_dict = {
                    "type": "upload failure",
                    "location": "CopyUploaderMixin.upload",
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
            self.info(f"Average transfer rate {round(np.nanmean(all_rates), 2)} MB/s")
        else:
            self.info(f"No files transferred.")
        return {"success": successes, "failure": errors}
