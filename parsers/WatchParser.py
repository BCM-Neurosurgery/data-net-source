from source.base import ParserCommon
from source.checkers.api import RuneAPICheckerMixin
from source.transformers import APIFetchTransformerMixin
from source.uploaders import BucketUploaderMixin


class WatchParser(RuneAPICheckerMixin, APIFetchTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
