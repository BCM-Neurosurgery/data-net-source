from source.common import ParserCommon
from source.checkers.local import StreamedFileCheckerMixin
from source.uploaders.simple import CopyUploaderMixin


class BlackrockChecker(StreamedFileCheckerMixin):
    initialize_files = ['.ccf', '.csr', '.sif', '.toc']
    streamed_files = ['.nev', '.ns3', '.ns5']
    stream_rate = 240.0
    reliability_factor = 2.0


class BlackrockParser(BlackrockChecker, CopyUploaderMixin, ParserCommon):
    """"""



