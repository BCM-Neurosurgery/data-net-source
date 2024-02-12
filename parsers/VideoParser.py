from source.common import ParserCommon
from source.checkers.local import DirectoryCheckerMixin
from source.uploaders.simple import BucketUploaderMixin


class VideoParser(DirectoryCheckerMixin, BucketUploaderMixin, ParserCommon):
    """"""
