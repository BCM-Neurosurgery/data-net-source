from source.common import ParserCommon
from parsers.blackrock import BlackrockChecker
from source.checkers.local import IndicatorFileCheckerMixin
from source.uploaders.datajoint import EMUBlackrockDJUploader


class DatalakeBRKChecker(IndicatorFileCheckerMixin, BlackrockChecker):
    """
    """

    def check(self):
        """Use the Indicator Checker to get the list of all files, and then sub select only the NSP files"""
        all_files = IndicatorFileCheckerMixin.check(self)

        failure = all_files['failure']
        to_do = self.filter_streamed_files(all_files['to do'])

        return {'to do': to_do, 'failure': failure}


class DataLakeBRKParser(DatalakeBRKChecker, EMUBlackrockDJUploader, ParserCommon):
    """Parser for inserting new BRK data that arrives in the data lake into DataJoint"""
