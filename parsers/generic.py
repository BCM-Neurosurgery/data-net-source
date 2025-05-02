from source.checkers.local.base import FileCheckerMixin
from source.uploaders.ssh import SCPUploaderMixin
from source.common import ParserCommon


class SCPFileParser(FileCheckerMixin, SCPUploaderMixin, ParserCommon):
    """Basic source parser for moving all files in a directory to a remote endpoint via SCP"""

