from source.checkers.local import FileCheckerMixin


class TRBDChecker(FileCheckerMixin):
    streamed_files = [".json"]
    stream_rate = 24 * 60 * 60  # New file every 24 hours
    reliability_factor = 1.1  # File durations are quite reliable, approx 1 min buffer in case of rounding error
