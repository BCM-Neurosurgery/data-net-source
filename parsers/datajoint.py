from source.common import ParserCommon
from parsers.blackrock import BlackrockChecker
from source.uploaders.datajoint import EMUBlackrockDJUploader


class DataLakeBRKParser(BlackrockChecker, EMUBlackrockDJUploader, ParserCommon):
    """Parser for inserting new BRK data that arrives in the data lake into DataJoint"""
