import os
import matlab.engine
import re
import shutil
from common.utils.time import unix_to_timestamps
from common.utils.ingest import storage_format_date


class ParserCommon:
    def __init__(self, input_folder):
        self.input_path = input_folder

    @staticmethod
    def pull_data():
        # Generic function to pull data to be parsed
        return None

    @staticmethod
    def upload_to_wasabi(self):
        # Generic function upload to wasabi
        return None


class RCSParser(ParserCommon):
    def __init__(self, input_folder):
        ParserCommon.__init__(self, input_folder)

    def full_parse(self):
        # self.pull_data() Skip for now until UCSF server is sorted out
        self.aggregate_data_sessions()
        self.anonymize_batch()
        self.convert_json_to_csv()
        # self.upload_to_wasabi() Need to figure out how to upload data to wasabi
        return None

    def pull_data(self):
        # add code that copies RCS data from UCSF server and saves to input_path
        return None

    def aggregate_data_sessions(self):
        directory = self.input_path
        unix_regex = 'Session([0-9]*)'

        for session_folder in os.listdir(directory):
            match = re.search(unix_regex, session_folder)
            if match:
                date = unix_to_timestamps(match.group(1), units='ms')
                date_str = storage_format_date(date)
                date_dir = os.path.join(directory, date_str)
                os.makedirs(date_dir, exist_ok=True)
                shutil.move(os.path.join(directory, session_folder), os.path.join(date_dir, session_folder))
        return None

    def start_matlab(self):
        # Start and return matlab engine to run matlab code in python
        return matlab.engine.start_matlab('-nojvm')

    def anonymize_batch(self):
        # Run matlab anonymize_batch.m code
        eng = self.start_matlab()
        eng.addpath(r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data-net-subject/source_data',
                    nargout=0)  # Path to data_analysis/openmind_processing folder
        # TODO: Edit path so it uses self.input_path and generically goes into the correct folder names
        eng.anonymize_batch_callable(r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data/rcs07/rcs'
                                     r'/combined_original')
        return None

    def convert_json_to_csv(self):
        # Run matlab convert_json_batch.m
        eng = self.start_matlab()
        eng.addpath(r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data-net-subject/source_data',
                    nargout=0)  # Path to data_analysis/openmind_processing folder
        # TODO: Edit path so it uses self.input_path and generically goes into the correct folder names
        eng.convert_json_batch_callable(r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data/rcs07/rcs'
                                        r'/combined_anonymized_json')
        return None

    def upload_to_wasabi(self):
        # Run aggregate data session code
        return None
