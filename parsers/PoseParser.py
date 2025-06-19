from source.common import ParserCommon
from source.checkers.local.base import DirectoryCheckerMixin
from source.transformers.openpose import OpenPoseTransformerMixin
from source.uploaders.simple import BucketUploaderMixin


class OpenPoseParser(DirectoryCheckerMixin, OpenPoseTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
