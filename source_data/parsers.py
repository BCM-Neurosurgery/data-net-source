import os
import matlab.engine
import re
import shutil
from common.utils.time import unix_to_timestamps
from common.utils.ingest import storage_format_date
from common.utils.rclone import copy, list_remote
from common.utils.rune import get_bilateral_watch_data, make_df_from_rune_accessor, get_client
import pandas as pd

class ParserCommon:
    #Upload_to_wasabi might be the only one that is common to all parsers
    def __init__(self, input_folder):
        self.input_path = input_folder

    @staticmethod
    def check_for_new_uploads(self):
        # Generic function to check if new data has uploaded
        return None

    @staticmethod
    def pull_data(self):
        # Generic function to pull data to be parsed
        return None

    @staticmethod
    def upload_to_wasabi(self, path_to_source, path_to_destination):
        # Generic function upload to wasabi
        #copy(path_to_source, path_to_destination)
        return None


class RCSParser(ParserCommon):
    # Parser class for RC+S data
    def __init__(self, input_folder):
        ParserCommon.__init__(self, input_folder)

    def full_parse(self):
        # self.pull_data() Skip for now until UCSF server is sorted out
        self.aggregate_data_sessions()
        self.anonymize_batch()
        self.convert_json_to_csv()
        # self.upload_to_wasabi() Need to figure out how to upload data to wasabi
        return None

    def check_for_new_uploads(self):
        # Check wasabi for most recent data folder.
        # Then check the ucsf server for any folders above that date.
        # if new folders save their names to download?
        return None

    def pull_data(self):
        # add code that copies RCS data from UCSF server and saves to input_path
        # uncomment below line (and add UCSF server info) to add secure copy of files from server
        # call('scp remote_username@10.10.0.2:/remote/directory DEST_HOST:local/destination')
        return None

    def aggregate_data_sessions(self):
        # Orginizes the session folders into date folders
        directory = self.input_path
        unix_regex = 'Session([0-9]*)'
        new_directory = directory[0:-8] + r'by_date'
        for session_folder in os.listdir(directory):
            match = re.search(unix_regex, session_folder)
            if match:
                date = unix_to_timestamps(match.group(1), units='ms')
                date_str = storage_format_date(date)
                date_dir = os.path.join(new_directory, date_str)
                os.makedirs(date_dir, exist_ok=True)
                shutil.copytree(os.path.join(directory, session_folder), os.path.join(date_dir, session_folder))

        return None

    def start_matlab(self):
        # Start and return matlab engine to run matlab code in python
        return matlab.engine.start_matlab('-nojvm')

    def anonymize_batch(self):
        # Run matlab anonymize_batch.m code
        eng = self.start_matlab()
        # TODO: Edit path so it uses self.input_path and generically goes into the correct folder names
        eng.addpath(r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data-net-subject/source_data',
                    nargout=0)  # Path to data_analysis/openmind_processing folder
        my_path = self.input_path[0:-8] + r'by_date'
        eng.anonymize_batch_callable(my_path)
        return None

    def convert_json_to_csv(self):
        # Run matlab convert_json_batch.m
        eng = self.start_matlab()
        # TODO: Edit path so it uses self.input_path and generically goes into the correct folder names
        eng.addpath(r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data-net-subject/source_data',
                    nargout=0)  # Path to data_analysis/openmind_processing folder
        my_path = self.input_path[0:-8] + r'anonymized_json'
        eng.convert_json_batch_callable(my_path)
        return None

    def upload_to_wasabi(self):
        # Upload folders to wasabi. TODO: Copy all newly generated date folders to wasabi
        return None

    def clean_directory(self):
        # delete non-anyonimized contents
        return None


class RuneParser(ParserCommon):
    #Pareser Class for the Rune data
    def __init__(self, input_folder):
        ParserCommon.__init__(self, input_folder)
        # Establish client connection
        self.myclient = get_client()

    def parse_rune_from_rcs_timestamps(self):
        folder_path = self.input_path  # '/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data/rcs07/'
        #TODO: change this to reflect wasabi not local directories
        date_dir = os.listdir(folder_path + 'rcs/combined_anonymized_json_csv/')

        if '.DS_Store' in date_dir:
            date_dir.remove('.DS_Store')

        for i in date_dir:
            session_dir = os.listdir(folder_path + 'rcs/combined_anonymized_json_csv/' + i)
            if '.DS_Store' in session_dir:
                session_dir.remove('.DS_Store')
            for j in session_dir:
                my_timestamps = self.get_timestamps(folder_path + 'rcs/combined_anonymized_json_csv/' + i + '/' + j)

                self.output_to_csv(folder_path, i, j, *self.timestamps_to_rune_data(my_timestamps))

    def check_for_new_uploads(self):
        # Check wasabi RCS for most recent data folder.
        # Then use the timestamps from those folders to get rune data
        return None

    def get_timestamps(self,path_to_folder):
        # Get first and last timestamp from rcs data
        neural_time_domain = pd.read_csv(path_to_folder + '/NeuralTimeDomain.csv')
        start = str(neural_time_domain["timestamp"].iloc[0])
        end = str(neural_time_domain["timestamp"].iloc[-1])
        time_range = [start[0:-4], end[0:-4]]
        return time_range

    def timestamps_to_rune_data(self,time_range):
        # pull rune data based on the time_range given. This time range is determined above and matches
        # the time ranges of the rcs data.
        wrist_params = {
            'patient_id': 'rcs07',
            'left_watch_id': '8QuY9OFb',
            'right_watch_id': 'RElEtNme',
            'time_range': time_range
        }
        rcs_params = {
            'patient_id': 'rcs07',
            'left_watch_id': 'NPC700419H',
            'right_watch_id': 'NPC700403H',
            'time_range': time_range
        }

        my_accel = get_bilateral_watch_data(self.myclient, 'accel', **wrist_params)
        my_rotation = get_bilateral_watch_data(self.myclient, 'rotation', **wrist_params)
        my_heart_rate = get_bilateral_watch_data(self.myclient, 'heart rate', **wrist_params)
        my_tremor = get_bilateral_watch_data(self.myclient, 'tremor', **wrist_params)
        my_tremor_severity = get_bilateral_watch_data(self.myclient, 'tremor severity', **wrist_params)
        my_dyskinesia = get_bilateral_watch_data(self.myclient, 'dyskinesia', **wrist_params)
        my_lfp = get_bilateral_watch_data(self.myclient, 'lfp', **wrist_params)
        my_band_power = get_bilateral_watch_data(self.myclient, 'band power', **wrist_params)

        return my_accel, my_rotation, my_heart_rate, my_tremor, my_tremor_severity, my_dyskinesia, my_lfp, my_band_power

    def output_to_csv(self, path, date, folder, my_accel, my_rotation, my_heart_rate, my_tremor, my_tremor_severity,
                      my_dyskinesia, my_lfp, my_band_power):
        #output all data to csv. Uses parallel path structure as the rcs data≥
        check_folder_left = os.path.isdir(path + 'rune/' + date + '/rune_left_' + folder[-27:-1])
        check_folder_right = os.path.isdir(path + 'rune/' + date + '/rune_right_' + folder[-27:-1])

        # If folder doesn't exist, then create it.
        if not check_folder_left:
            os.makedirs(path + 'rune/' + date + '/rune_left_' + folder[-27:-1])
        if not check_folder_right:
            os.makedirs(path + 'rune/' + date + '/rune_right_' + folder[-27:-1])

        my_accel[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/accel.csv')
        my_accel[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/accel.csv')

        my_rotation[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/rotation.csv')
        my_rotation[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/rotation.csv')

        my_heart_rate[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/heart_rate.csv')
        my_heart_rate[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/heart_rate.csv')

        my_tremor[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/tremor.csv')
        my_tremor[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/tremor.csv')

        my_tremor_severity[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/tremor_severity.csv')
        my_tremor_severity[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/tremor_severity.csv')

        my_dyskinesia[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/dyskinesia.csv')
        my_dyskinesia[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/dyskinesia.csv')

        my_lfp[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/lfp.csv')
        my_lfp[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/lfp.csv')

        my_band_power[0].to_csv(path + 'rune/' + date + '/rune_left_' + folder[-27:-1] + '/band_power.csv')
        my_band_power[1].to_csv(path + 'rune/' + date + '/rune_right_' + folder[-27:-1] + '/band_power.csv')

    def upload_to_wasabi(self):
        #Copy the csv files to wasabi
        #copy(self.inputpath/Date/*, secret_sauce:/rcs07/rcs_v2/:
        return None

    def clean_directory(self):
        #Delete any local files that have been uploaded to wasabi
        return None
