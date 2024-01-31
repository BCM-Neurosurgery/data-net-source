import os
import shutil
import sys
from abc import abstractmethod, ABC


class BaseUploader(ABC):

    @property
    @abstractmethod
    def uploader_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseUploader"

    @abstractmethod
    def upload(self, ready):
        return {}  # Should return a dict describing successful uploads and failures


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

        errors = []
        successes = []

        for filename in ready:
            destination = 'Failed to determine!'
            try:
                rel_filepath = os.path.relpath(filename, start=self.source_location)
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
            'successes': successes, 'errors': errors
        }


