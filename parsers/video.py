from source.common import ParserCommon
from source.checkers.local import DirectoryCheckerMixin
from source.uploaders.simple import CopyUploaderMixin, SCPUploaderMixin


class VideoParser(DirectoryCheckerMixin, CopyUploaderMixin, ParserCommon):
    """"""
