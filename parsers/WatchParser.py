from source.common import ParserCommon
from source.checkers.api import RuneAPICheckerMixin
from source.transformers.api import RuneFetchTransformerMixin
from source.uploaders.simple import BucketUploaderMixin


class WatchParser(RuneAPICheckerMixin, RuneFetchTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
