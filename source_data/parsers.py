import os
import matlab.engine
import re
import shutil
from common.utils.time import unix_to_timestamps
from common.utils.ingest import storage_format_date
from common.utils.rclone import copy, list_remote
from common.utils.rune import get_watch_data, get_client
import subprocess
import pandas as pd
import numpy as np


class ParserCommon:
    # Upload_to_wasabi might be the only one that is common to all parsers
    def __init__(self):
        pass

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
        # copy(path_to_source, path_to_destination)
        return None


class RCSParser(ParserCommon):
    # Parser class for RC+S data
    def __init__(self):
        ParserCommon.__init__(self)

    def full_parse(self):
        print('START')
        for i in ['L', 'R']:
            ucsf_all_files = subprocess.check_output(["ssh", "rbechto2@10.37.129.11", "ls",
                                                      "/media/dropbox_hdd/Starr\ Lab\ Dropbox/RC+S\ Patient\ Un-Synced\ Data/RCS07\ Un-Synced\ Data/SummitData/SummitContinuousBilateralStreaming/RCS07" + i]).decode(
                "utf-8")
            ucsf_session_names = [i for i in ucsf_all_files.split() if 'Session' in i]
            self.download_session_data(i, self.get_new_session_names(np.asarray(ucsf_session_names)))

        print('Aggregate')
        self.aggregate_data_sessions()
        print('Anonymize')
        self.anonymize_batch()
        print('To csv')
        self.convert_json_to_csv()
        # self.upload_to_wasabi() # uncomment when ready
        # self.clean_directory() # uncomment when ready
        return None

    def get_new_session_names(self, ucsf_session_names):
        # returns a list of new session folder names
        # compares current ucsf server session dates to current wasabi dates
        # and returns session on dates that are on ucsf server, but not wasabi

        current_dates = list_remote('rcs07/rcs_v2/')
        if '.DS_Store\n' in current_dates:
            current_dates.remove('.DS_Store\n')

        current_dates = current_dates[0:-3]
        current_dates = max([int(i[0:-2]) for i in current_dates])

        session_unix_times = [int(i[7:]) for i in ucsf_session_names]
        ucsf_session_dates = np.asarray([unix_to_timestamps(i).strftime('%Y%m%d') for i in session_unix_times])
        new_sessions_mask = np.asarray(ucsf_session_dates, dtype=int) > current_dates

        new_session_names = ucsf_session_names[new_sessions_mask]
        return new_session_names

    def download_session_data(self, side, session_folder_names):
        # Make a list of session date directory paths for the scp command to use
        session_paths = [
            "rbechto2@10.37.129.11:'/media/dropbox_hdd/Starr Lab Dropbox/RC+S Patient Un-Synced Data/RCS07 Un-Synced Data/SummitData/SummitContinuousBilateralStreaming/RCS07" + side + f"/{i}'"
            for i in session_folder_names]
        p = subprocess.Popen(["scp", "-r", *session_paths, "./temp/combined_original/"])
        # TODO: change to p.communicate and get the output and error message
        p.wait(1800)
        return None

    def aggregate_data_sessions(self):
        # Organizes the session folders into date folders
        directory = './temp/combined_original'
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
        eng.addpath(r'./', nargout=0)  # Path to matlab functions
        my_path = r'./combined_by_date'
        eng.anonymize_batch_callable(my_path)
        return None

    def convert_json_to_csv(self):
        # Run matlab convert_json_batch.m
        eng = self.start_matlab()
        eng.addpath(r'./', nargout=0)  # Path to data_analysis/openmind_processing folder
        my_path = r'combined_anonymized_json'
        eng.convert_json_batch_callable(my_path)
        return None

    def upload_to_wasabi(self):
        # Upload folders to wasabi.
        # copys all data in final processed date folder and copies to wasabi
        copy('./temp/combined_anonymized_json_csv/.', 'secret_sauce:/rcs07/rcs_v2/')
        return None

    def clean_directory(self):
        # Delete all data from local machine (use after upload_to_wasabi)
        shutil.rmtree('./temp/')
        os.mkdir('./temp')
        return None


class RuneParser(ParserCommon):
    # Pareser Class for the Rune data
    def __init__(self, input_folder):
        ParserCommon.__init__(self, input_folder)
        # Establish client connection
        self.myclient = get_client()

    def parse_rune_from_rcs_timestamps(self):
        folder_path = self.input_path  # '/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data/rcs07/'
        # TODO: change this to reflect wasabi not local directories
        date_dir = os.listdir(folder_path + 'rcs/combined_anonymized_json_csv/')

        if '.DS_Store' in date_dir:
            date_dir.remove('.DS_Store')

        for i in date_dir:
            session_dir = os.listdir(folder_path + 'rcs/combined_anonymized_json_csv/' + i)
            if '.DS_Store' in session_dir:
                session_dir.remove('.DS_Store')
            for j in session_dir:
                my_timestamps = self.get_timestamps(folder_path + 'rcs/combined_anonymized_json_csv/' + i + '/' + j)
                self.output_to_csv(folder_path, i, j, *self.timestamps_to_rune_data(my_timestamps, j))

    def check_for_new_uploads(self):
        # Check wasabi RCS for most recent data folder.
        # Then use the timestamps from those folders to get rune data
        return None

    def get_timestamps(self, path_to_folder):
        # Get first and last timestamp from rcs data
        neural_time_domain = pd.read_csv(path_to_folder + '/NeuralTimeDomain.csv')
        start = str(neural_time_domain["timestamp"].iloc[0])
        end = str(neural_time_domain["timestamp"].iloc[-1])
        time_range = [start[0:-4], end[0:-4]]
        return time_range

    def get_side(self, folder_name):
        if 'left' in folder_name:
            return True
        if 'right' in folder_name:
            return False

    def get_params(self, side, dual_sided_params):
        if side:
            return {
                'patient_id': dual_sided_params['patient_id'],
                'device_id': dual_sided_params['left_watch_id'],
                'start_time': dual_sided_params['time_range'][0],
                'end_time': dual_sided_params['time_range'][1]}
        else:
            return {
                'patient_id': dual_sided_params['patient_id'],
                'device_id': dual_sided_params['right_watch_id'],
                'start_time': dual_sided_params['time_range'][0],
                'end_time': dual_sided_params['time_range'][1]}

    def timestamps_to_rune_data(self, timestamps, folder_name):

        wrist_params = {
            'patient_id': 'rcs07',
            'left_watch_id': '8QuY9OFb',
            'right_watch_id': 'RElEtNme',
            'time_range': timestamps
        }
        rcs_params = {
            'patient_id': 'rcs07',
            'left_watch_id': 'NPC700419H',
            'right_watch_id': 'NPC700403H',
            'time_range': timestamps
        }

        my_accel = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), wrist_params),
                                  'accel').set_index(
            'timestamp')
        my_rotation = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), wrist_params),
                                     'rotation').set_index(
            'timestamp')
        my_heart_rate = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), wrist_params),
                                       'heart rate').set_index('timestamp')
        my_tremor = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), wrist_params),
                                   'tremor').set_index(
            'timestamp')
        my_tremor_severity = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), wrist_params),
                                            'tremor severity').set_index('timestamp')
        my_dyskinesia = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), wrist_params),
                                       'dyskinesia').set_index('timestamp')
        my_lfp = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), rcs_params),
                                'lfp').set_index('timestamp')
        my_band_power = get_watch_data(self.myclient, self.get_params(self.get_side(folder_name), rcs_params),
                                       'band power').set_index(
            'timestamp')

        return my_accel, my_rotation, my_heart_rate, my_tremor, my_tremor_severity, my_dyskinesia, my_lfp, my_band_power

    def output_to_csv(self, path, date, folder, my_accel, my_rotation, my_heart_rate, my_tremor, my_tremor_severity,
                      my_dyskinesia, my_lfp, my_band_power):

        if self.get_side(folder):
            full_path = path + 'rune/' + date + '/rune_left_' + folder[-27:]
        else:
            full_path = path + 'rune/' + date + '/rune_right_' + folder[-27:]

        # If folder doesn't exist, then create it.
        if not os.path.isdir(full_path):
            os.makedirs(full_path)

        my_accel.to_csv(full_path + '/accel.csv')
        my_rotation.to_csv(full_path + '/rotation.csv')
        my_heart_rate.to_csv(full_path + '/heart_rate.csv')
        my_tremor.to_csv(full_path + '/tremor.csv')
        my_tremor_severity.to_csv(full_path + '/tremor_severity.csv')
        my_dyskinesia.to_csv(full_path + '/dyskinesia.csv')
        my_lfp.to_csv(full_path + '/lfp.csv')
        my_band_power.to_csv(full_path + '/band_power.csv')

    def upload_to_wasabi(self):
        # Copy the csv files to wasabi
        # copy(self.inputpath/Date/*, secret_sauce:/rcs07/rcs_v2/:
        return None

    def clean_directory(self):
        # Delete any local files that have been uploaded to wasabi
        return None
