from abc import abstractmethod, ABC


class BaseUploader(ABC):

    @property
    @abstractmethod
    def uploader_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseUploader"

    @abstractmethod
    def upload(self, ):
        return {}  # Should return a dict describing successful uploads and failures


class BucketUploaderMixin(BaseUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """

    uploader_name = "BucketUploaderMixin"

    def upload(self, ):
        raise NotImplementedError

