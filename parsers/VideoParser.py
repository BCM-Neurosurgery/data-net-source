from source.base import ParserCommon
from source.checkers import DirectoryCheckerMixin
from source.transformers import NullTransformerMixin
from source.uploaders import BucketUploaderMixin


class VideoParser(DirectoryCheckerMixin, NullTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
