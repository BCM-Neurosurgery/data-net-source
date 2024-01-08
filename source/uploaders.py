from abc import abstractmethod, ABC


class BaseUploader(ABC):

    @abstractmethod
    def upload(self, ):
        return []  # Should return a dict describing successful uploads and failures


class BucketUploaderMixin(BaseUploader):
    """
    Uploader that moves files from local storage to an S3-style bucket in the cloud
    """


