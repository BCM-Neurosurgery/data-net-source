from source.common import ParserCommon
from source.checkers.local.stream import StreamedFileCheckerMixin
from source.uploaders.simple import CopyUploaderMixin
from source.uploaders.ssh import SCPUploaderMixin
from source.uploaders.rsync import RsyncUploaderMixin


class StreamedVideoCheckerMixin(StreamedFileCheckerMixin):
    """Streamed file checker specifically for video files"""
    initialize_files = []
    streamed_files = ['.mp4', '.json']
    stream_rate = 60*10  # New file every 10 minutes
    reliability_factor = 1.1  # File durations are quite reliable, approx 1 min buffer in case of rounding error


class VideoParser(StreamedVideoCheckerMixin, CopyUploaderMixin, ParserCommon):
    """"""


class VideoSCPParser(StreamedVideoCheckerMixin, SCPUploaderMixin, ParserCommon):
    """"""


class VideoRsyncParser(StreamedVideoCheckerMixin, RsyncUploaderMixin, ParserCommon):
    """Upload queued recording files with rsync over SSH."""
