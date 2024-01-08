from source.base import ParserCommon
from source.checkers import DirectoryCheckerMixin
from source.transformers import OpenMindTransformerMixin
from source.uploaders import BucketUploaderMixin


class RCSParser(DirectoryCheckerMixin, OpenMindTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
