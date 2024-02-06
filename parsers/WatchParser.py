from source.base import ParserCommon
from source.checkers.api import RuneAPICheckerMixin
from source.transformers import RuneFetchTransformerMixin
from source.uploaders import BucketUploaderMixin


class WatchParser(RuneAPICheckerMixin, RuneFetchTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
