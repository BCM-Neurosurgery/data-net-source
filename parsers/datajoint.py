from source.common import ParserCommon
from parsers.blackrock import BlackrockChecker
from source.checkers.local import IndicatorFileCheckerMixin
from source.uploaders.datajoint import EMUBlackrockDJUploader


class DatalakeBRKChecker(BlackrockChecker, IndicatorFileCheckerMixin):
    """
    """

    def check(self):
        to_check = self.parse_indicators()
        to_do = []
        failure = []

        for directory in to_check:
            try:
                found_here = BlackrockChecker.check(self)
            except FileNotFoundError as e:
                raise FileNotFoundError(f'Indicated patient not found! \n  {e.filename}')
            to_do.extend(found_here['to do'])
            failure.extend(found_here['failure'])

        return {'to do': to_do, 'failure': failure}


class DataLakeBRKParser(DatalakeBRKChecker, EMUBlackrockDJUploader, ParserCommon):
    """Parser for inserting new BRK data that arrives in the data lake into DataJoint"""
