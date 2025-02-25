import os
import shutil
import subprocess
import matlab

import numpy as np
import pandas as pd


from source.transformers.base import BaseTransformer


class OpenMindTransformerMixin(BaseTransformer):

    transformer_name = "OpenMindTransformer"

    def transform(self, tasks):
        """
        Convert the raw JSON files from the Medtronic summit RC+S API to anonymized CSV files using OpenMind code
        https://github.com/openmind-consortium/Analysis-rcs-data
        """
        # TODO: move all of Raph's code here

        print('Aggregate')
        self.aggregate_data_sessions()
        print('Anonymize')
        self.anonymize_batch()
        print('To csv')
        self.convert_json_to_csv()

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