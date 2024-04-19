from source.common import ParserCommon
from source.checkers.local import FileCheckerMixin
from source.uploaders.datajoint import EMUBlackrockDJUploader


class DataLakeBRKParser(FileCheckerMixin, EMUBlackrockDJUploader, ParserCommon):
    """Parser for inserting new BRK data that arrives in the data lake into DataJoint"""
