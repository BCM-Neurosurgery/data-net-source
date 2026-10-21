from source.common import ParserCommon
from source.checkers.local.stream import StreamedFileCheckerMixin
from source.uploaders.simple import CopyUploaderMixin
from source.uploaders.ssh import SCPUploaderMixin
from source.uploaders.rsync import RsyncUploaderMixin


class BlackrockChecker(StreamedFileCheckerMixin):
    initialize_files = ['.ccf', '.csr', '.sif', '.toc']
    streamed_files = ['.nev'] + [f'.ns{i}' for i in range(1, 10)]
    stream_rate = 60*10  # New file every 10 minutes
    reliability_factor = 1.1  # File durations are quite reliable, approx 1 min buffer in case of rounding error


class BlackrockRemoteParser(BlackrockChecker, SCPUploaderMixin, ParserCommon):
    """Parser for uploading new blackrock data to the remote server"""


class BlackrockLocalParser(BlackrockChecker, CopyUploaderMixin, ParserCommon):
    """Parser for copying new blackrock data to the local backup"""


class BlackrockRsyncParser(BlackrockChecker, RsyncUploaderMixin, ParserCommon):
    """Upload queued recording files with rsync over SSH."""
