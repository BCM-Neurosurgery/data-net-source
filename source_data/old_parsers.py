import os
import matlab.engine
import re
import shutil
from common.utils.time import unix_to_timestamps, timestamp_to_unix
from common.utils.ingest import storage_format_date
from common.utils.rclone import copy, list_remote
from common.utils.rune import get_watch_data, get_client
import subprocess
import pandas as pd
import numpy as np
from datetime import timedelta

class ParserCommon:
    # Upload_to_wasabi might be the only one that is common to all parsers
    def __init__(self):
        self.folder_path = '/home/weill2/Documents/data-net-subject/source_data/temp'

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
            self.download_session_data(i, self.get_new_session_names(i))

        print('Aggregate')
        self.aggregate_data_sessions()
        print('Anonymize')
        self.anonymize_batch()
        print('To csv')
        self.convert_json_to_csv()
        print('Uploading to Wasabi')
        self.upload_to_wasabi()
        print('Clear Temp Directory After Upload')
        self.clean_directory()
        return None

    def get_new_session_names(self, side):
        # returns a list of new session folder names
        # compares current ucsf server session dates to current wasabi dates
        # and returns session on dates that are on ucsf server, but not wasabi

        current_session_on_wasabi = pd.read_csv('./saved_session_logs/processed_sessions_' + side + '.csv').to_numpy()[:, 1]
        ucsf_all_files = subprocess.check_output(["ssh", "rbechto2@10.37.129.11", "ls",
                                                  "/media/dropbox_hdd/Starr\ Lab\ Dropbox/RC+S\ Patient\ Un-Synced\ Data/RCS07\ Un-Synced\ Data/SummitData/SummitContinuousBilateralStreaming/RCS07" + side]).decode(
            "utf-8")
        ucsf_session_names = [i for i in ucsf_all_files.split() if 'Session' in i]
        new_session_folders = list(set(ucsf_session_names) - set(current_session_on_wasabi))
        updated_ucsf_session_names = np.sort(np.unique(np.concatenate((list(current_session_on_wasabi),new_session_folders))))

        print(new_session_folders)
        # removed _update from file name once done building the code
        pd.Series(updated_ucsf_session_names).to_frame().to_csv(
            './saved_session_logs/processed_sessions_' + side + '_updated.csv')

        return np.array(new_session_folders)

    def download_session_data(self, side, session_folder_names):
        # Make a list of session date directory paths for the scp command to use
        session_paths = ["rbechto2@10.37.129.11:'/media/dropbox_hdd/Starr Lab Dropbox/RC+S Patient Un-Synced Data/RCS07 Un-Synced Data/SummitData/SummitContinuousBilateralStreaming/RCS07" + side + f"/{i}'" for i in session_folder_names]
        p = subprocess.Popen(["scp", "-r", *session_paths, "./temp/combined_original/"])
        # TODO: change to p.communicate and get the output and error message
        p.wait(1800)

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
        my_path = r'./temp/combined_by_date'
        eng.anonymize_batch_callable(my_path)
        return None

    def convert_json_to_csv(self):
        # Run matlab convert_json_batch.m
        eng = self.start_matlab()
        eng.addpath(r'./', nargout=0)  # Path to data_analysis/openmind_processing folder
        my_path = r'./temp/combined_anonymized_json'
        eng.convert_json_batch_callable(my_path)
        return None

    def upload_to_wasabi(self):
        # Upload folders to wasabi.
        # copys all data in final processed date folder and copies to wasabi
        p = subprocess.Popen(['rclone' ' copy' ' /home/weill2/Documents/data-net-subject/source_data/temp/combined_anonymized_json_csv/' ' secret_sauce:/rcs07/rcs_v2/'],shell=True)
        # TODO: change to p.communicate and get the output and error message
        p.wait(1800)
        return None

    def clean_directory(self):
        # Delete all data from local machine (use after upload_to_wasabi)
        shutil.rmtree('/home/weill2/Documents/data-net-subject/source_data/temp/')
        os.mkdir('/home/weill2/Documents/data-net-subject/source_data/temp/')
        os.mkdir('/home/weill2/Documents/data-net-subject/source_data/temp/combined_original')
        shutil.move("/home/weill2/Documents/data-net-subject/source_data/saved_session_logs/processed_sessions_L_updated.csv", "/home/weill2/Documents/data-net-subject/source_data/saved_session_logs/processed_sessions_L.csv")
        shutil.move("/home/weill2/Documents/data-net-subject/source_data/saved_session_logs/processed_sessions_R_updated.csv", "/home/weill2/Documents/data-net-subject/source_data/saved_session_logs/processed_sessions_R.csv")
        return None



class RuneParser(ParserCommon):
    # Pareser Class for the Rune data
    def __init__(self):
        ParserCommon.__init__(self)
        # Establish client connection
        self.myclient = get_client()

    def full_parse(self):

        rcs_dates = list_remote('rcs07/rcs_v2')
        watch_dates = list_remote('rcs07/watch')
        if '.DS_Store\n' in rcs_dates:
            rcs_dates.remove('.DS_Store\n')
        if '.DS_Store\n' in watch_dates:
            watch_dates.remove('.DS_Store\n')

        new_session_folders = list(set(rcs_dates) - set(watch_dates))
        new_session_folders = [i[0:-2] for i in new_session_folders]

        for i in new_session_folders:
            print('Date: ' + i)
            my_timestamps = self.get_timestamps(i)

            print('Left')
            self.output_to_csv(self.folder_path, i, True,
                               *self.timestamps_to_rune_data(my_timestamps, True))  # Left side Data

            print('Right')
            self.output_to_csv(self.folder_path, i, False,
                               *self.timestamps_to_rune_data(my_timestamps, False))  # Right side Data
        print('Uploading to Wasabi')
        self.upload_to_wasabi()
        print('Cleaning Temp Directory')
        self.clean_directory()

    def get_timestamps(self, data_date):

        if '.DS_Store' in data_date:
            data_date.remove('.DS_Store')
        start_of_day_unix_timestamp = pd.Timestamp(year=int(data_date[0:4]), month=int(data_date[4:6]),
                                                   day=int(data_date[6:]))
        start_of_day_unix_timestamp.tz_localize(tz='America/Los_Angeles')
        end_of_day_unix_timestamp = start_of_day_unix_timestamp + timedelta(days=1)
        time_range = timestamp_to_unix([start_of_day_unix_timestamp, end_of_day_unix_timestamp])
        return time_range

    def get_params(self, side, dual_sided_params):
        if side:
            return {
                'patient_id': dual_sided_params['patient_id'],
                'device_id': dual_sided_params['left_watch_id'],
                'start_time': dual_sided_params['time_range'][0],
                'end_time': dual_sided_params['time_range'][1]
            }
        else:
            return {
                'patient_id': dual_sided_params['patient_id'],
                'device_id': dual_sided_params['right_watch_id'],
                'start_time': dual_sided_params['time_range'][0],
                'end_time': dual_sided_params['time_range'][1]
            }

    def timestamps_to_rune_data(self, timestamps, side):
        myclient = get_client()

        wrist_params = {
            'patient_id': 'rcs07',
            'left_watch_id': '8QuY9OFb',
            'right_watch_id': 'Om3Cm3Kz',
            'time_range': timestamps
        }
        rcs_params = {
            'patient_id': 'rcs07',
            'left_watch_id': 'NPC700419H',
            'right_watch_id': 'NPC700403H',
            'time_range': timestamps
        }

        print('Reading in Apple Watch Accel Data with Gravity')
        my_accel = get_watch_data(myclient, self.get_params(side, wrist_params), 'accel').set_index('timestamp')

        print('Reading in Apple Watch Accel Data without Gravity')
        my_accel_wo_gravity = get_watch_data(myclient, self.get_params(side, wrist_params),
                                             'accel without gravity').set_index('timestamp')

        print('Reading in Apple Watch Rotation Data')
        my_rotation = get_watch_data(myclient, self.get_params(side, wrist_params), 'rotation').set_index('timestamp')

        print('Reading in Apple Watch Heart Rate Data')
        my_heart_rate = get_watch_data(myclient, self.get_params(side, wrist_params), 'heart rate').set_index(
            'timestamp')

        print('Reading in Apple Watch Tremor Data')
        my_tremor = get_watch_data(myclient, self.get_params(side, wrist_params), 'tremor').set_index('timestamp')

        print('Reading in Apple Watch Tremor Severity Data')
        my_tremor_severity = get_watch_data(myclient, self.get_params(side, wrist_params), 'tremor severity').set_index(
            'timestamp')

        print('Reading in Apple Watch Dysinesia Data')
        my_dyskinesia = get_watch_data(myclient, self.get_params(side, wrist_params), 'dyskinesia').set_index(
            'timestamp')

        print('Reading in RC+S LFP Data')
        my_lfp = get_watch_data(myclient, self.get_params(side, rcs_params), 'lfp').set_index('timestamp')

        print('Reading in RC+S Band Power Data')
        my_band_power = get_watch_data(myclient, self.get_params(side, rcs_params), 'band power').set_index('timestamp')

        return my_accel, my_accel_wo_gravity, my_rotation, my_heart_rate, my_tremor, my_tremor_severity, my_dyskinesia, my_lfp, my_band_power

    def output_to_csv(self, path, date, side, my_accel, my_accel_wo_gravity, my_rotation, my_heart_rate, my_tremor,
                      my_tremor_severity, my_dyskinesia, my_lfp, my_band_power):
        print('Outputting Data to CSV')
        if side:
            full_path_watch = path + '/watch/' + date + '/left/'
            full_path_rune_rcs = path + '/rcs_rune/' + date + '/left/'
        else:
            full_path_watch = path + '/watch/' + date + '/right/'
            full_path_rune_rcs = path + '/rcs_rune/' + date + '/right/'

        # If folder doesn't exist, then create it.
        if not os.path.isdir(full_path_watch):
            os.makedirs(full_path_watch)
        if not os.path.isdir(full_path_rune_rcs):
            os.makedirs(full_path_rune_rcs)

        my_accel.to_csv(full_path_watch + 'accel.csv')
        my_accel_wo_gravity.to_csv(full_path_watch + 'accel_without_gravity.csv')
        my_rotation.to_csv(full_path_watch + 'rotation.csv')
        my_heart_rate.to_csv(full_path_watch + 'heart_rate.csv')
        my_tremor.to_csv(full_path_watch + 'tremor.csv')
        my_tremor_severity.to_csv(full_path_watch + 'tremor_severity.csv')
        my_dyskinesia.to_csv(full_path_watch + 'dyskinesia.csv')
        my_lfp.to_csv(full_path_rune_rcs + 'lfp.csv')
        my_band_power.to_csv(full_path_rune_rcs + 'band_power.csv')

    def upload_to_wasabi(self):
        p = subprocess.Popen(['rclone' ' copy' ' ./temp/watch/' 
                              ' secret_sauce:/rcs07/watch/'], shell=True)
        p = subprocess.Popen(['rclone' ' copy' ' ./temp/rcs_rune/' 
                              ' secret_sauce:/rcs07/rcs_rune/'], shell=True)
        # TODO: change to p.communicate and get the output and error message
        p.wait(1800)

        return None

    def clean_directory(self):
        # Delete any local files that have been uploaded to wasabi
        shutil.rmtree('./temp/watch')
        shutil.rmtree('./temp/rcs_rune')
        return None

