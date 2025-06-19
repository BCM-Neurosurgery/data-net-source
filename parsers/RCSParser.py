from source.common import ParserCommon
from source.checkers.local.base import DirectoryCheckerMixin
from source.transformers.matlab import OpenMindTransformerMixin
from source.uploaders.simple import BucketUploaderMixin


class RCSParser(DirectoryCheckerMixin, OpenMindTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
