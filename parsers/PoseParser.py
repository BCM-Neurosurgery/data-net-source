from source.common import ParserCommon
from source.checkers.local import DirectoryCheckerMixin
from source.transformers.openpose import OpenPoseTransformerMixin
from source.uploaders.simple import BucketUploaderMixin


class OpenPoseParser(DirectoryCheckerMixin, OpenPoseTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
