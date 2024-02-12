import os
import shutil
import sys

from source.uploaders.base import BaseUploader


class BucketUploaderMixin(BaseUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """

    uploader_name = "BucketUploaderMixin"

    def upload(self, ready):
        raise NotImplementedError


class CopyUploaderMixin(BaseUploader):

    uploader_name = "SimpleCopyMixin"

    def upload(self, ready):

        errors = ready['failure']
        successes = ready['to upload']

        for filename in ready:
            destination = 'Failed to determine!'
            try:
                rel_filepath = os.path.relpath(filename, start=self.source_location)

                # Make sure the destination folder exists
                folder_path = os.path.join(self.target_location, os.path.dirname(rel_filepath))
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                destination = os.path.join(self.target_location, rel_filepath)
                shutil.copy(filename, destination)
            except Exception as e:
                errors.append({
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': filename,
                    'destination': destination,
                    'error': str(e),
                    'trace': sys.exc_info()
                })
            else:
                successes.append({
                    'type': 'upload success',
                    'filename': filename,
                    'destination': destination,
                })

        return {
            'success': successes, 'failure': errors
        }
