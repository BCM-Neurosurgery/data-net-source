from source.common import ParserCommon
from source.checkers.local import StreamedFileCheckerMixin
from source.uploaders.simple import CopyUploaderMixin
from source.uploaders.ssh import SCPUploaderMixin


class TRBDChecker(StreamedFileCheckerMixin):
    streamed_files = [
        "daily_activity.json",
        "daily_sleep.json",
        "daily_stress.json",
        "sleep.json",
    ]
    stream_rate = 24 * 60 * 60  # New file every 24 hours
    reliability_factor = 1.1  # File durations are quite reliable, approx 1 min buffer in case of rounding error


class TRBDRemoteParser(TRBDChecker, SCPUploaderMixin, ParserCommon):
    """Parser for uploading new TRBD data to the remote server"""


class TRBDLocalParser(TRBDChecker, CopyUploaderMixin, ParserCommon):
    """Parser for copying new TRBD data to the local backup"""
