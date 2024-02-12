from abc import ABC, abstractmethod


class ParserCommon(ABC):

    """
    Each parser must consist of 3 parts:
        - A Checker: check for new data to be processed, and saves completion once data is uploaded
        - A Transformer: apply any necessary transformations to the data
        - A Uploader: send the ready data up to the data lake

    Each parser may also include any of the following:
        - A logger: which
    """

    checker_name = "NullChecker"
    transformer_name = "NullTransformer"
    uploader_name = "NullUploader"
    notifier_name = "NullNotifier"

    def __init__(self, source, middle, target):
        """
        Generic creation for all parsers.

        :param source: location to check for new data to be processed
        :param middle: potentially temporary location to store intermediate processed data
        :param target: final location for the parser to leave the ready data
        """
        self.source_location = source
        self.middle_location = middle
        self.target_location = target

    def process(self):
        to_do = self.check()
        if to_do:
            ready = self.transform(to_do)
            complete = self.upload(ready)
        else:
            complete = None
        self.save(complete)

    def describe_parser(self):
        return {
            "git commit": "commitHash",  # TODO: implement commit hashing
            "base": str(type(self)),
            "checker": self.checker_name,
            "transformer": self.transformer_name,  # Defined in the TransformerMixin
            "uploader": self.uploader_name  # Defined in the UploaderMixin
        }

    def check(self):
        """
        Check should look for new data that needs to be uploaded
        See source.checkers.base.BaseChecker for details

        Default is the null checker which does nothing.
        """
        return {'to do': [], 'failure': []}

    def transform(self, tasks):
        """
        Convert the raw data files into a form that is ready for upload
        See source.transformers.base.BaseTransformer for details

        Default is null transformation that does nothing, so just pass back the original files as ready for upload
        """
        return {'to upload': tasks['to do'], 'failure': tasks['failure']}

    def upload(self, ready):
        """
        Upload the ready data files to the data lake with confirmation
        See source.uploaders.base.BaseUploader for details

        Default is NullUploader, which does nothing.
        """
        return {'success': ready['to upload'], 'failure': ready['failure']}

    @abstractmethod
    def save(self, completed):
        """Save the completed files to a log so that they are not re-uploaded"""

    def metadata(self):
        """
        Get the metadata about the data being parsed as a dictionary

        Uploaders should override this method to add additional metadata, and include the contents here
        :return:
        """
        meta = {}
        # TODO: Add some basic common metadata
        return meta