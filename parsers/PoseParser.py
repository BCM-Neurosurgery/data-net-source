from source.base import ParserCommon
from source.checkers import DirectoryCheckerMixin
from source.transformers import OpenPoseTransformerMixin
from source.uploaders import BucketUploaderMixin


class OpenPoseParser(DirectoryCheckerMixin, OpenPoseTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
