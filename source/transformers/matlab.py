import os
import shutil
import subprocess
import matlab.engine
from common.utils.time import unix_to_timestamps
from common.utils.ingest import storage_format_date
import numpy as np
import pandas as pd
import re


from source.transformers.base import BaseTransformer


class OpenMindTransformerMixin(BaseTransformer):

    transformer_name = "OpenMindTransformer"

    def transform(self, tasks):
        """
        Convert the raw JSON files from the Medtronic summit RC+S API to anonymized CSV files using OpenMind code
        https://github.com/openmind-consortium/Analysis-rcs-data
        """

        self.info("Aggregate data session")
        self.aggregate_data_sessions()
        
        #print('Anonymize')
        #self.anonymize_batch()
        
        self.info("Convert JSON to CSV")
        failures = self.convert_json_to_csv()

        failures_ = []
        for f in failures:
            failures.append({
                "filename": f,
                "type": "folder",
            })

        # ready = {'to upload': tasks['to do'], 'failure': tasks['failure']}
        ready = {'to upload': [], 'failure': failures}

        return ready

    def aggregate_data_sessions(self):
        # Organizes the session folders into date folders
        directory = self.source_location["path"]  # './temp/combined_original'
        unix_regex = 'Session([0-9]*)'

        #new_directory = directory[0:-8] + r'by_date'
        new_directory = self.middle_location["path"]

        file_cnt = 0
        for session_folder in os.listdir(directory):
            match = re.search(unix_regex, session_folder)
            if match:
                date = unix_to_timestamps(match.group(1), units='ms')
                date_str = storage_format_date(date)
                date_dir = os.path.join(new_directory, date_str)
                os.makedirs(date_dir, exist_ok=True)
                if not os.path.exists(os.path.join(date_dir, session_folder)):
                    shutil.copytree(os.path.join(directory, session_folder), os.path.join(date_dir, session_folder))
                    if self.LIMIT_FILES_COPY != -1:
                        file_cnt += 1
                        if file_cnt > self.LIMIT_FILES_COPY:
                            break
        return None

    def start_matlab(self):
        # Start and return matlab engine to run matlab code in python
        return 

    def anonymize_batch(self):
        # Run matlab anonymize_batch.m code
        eng = self.start_matlab()
        eng.addpath(r'scripts/openmind', nargout=0)  # Path to matlab functions
        my_path = r'./temp/combined_by_date'
        eng.anonymize_batch_callable(my_path)
        return None

    def convert_json_to_csv(self):

        my_path = self.middle_location["path"]
    
        with matlab.engine.start_matlab('-nojvm') as eng:
            eng.addpath(r'scripts/openmind', nargout=0)                     
            failures = eng.convert_json_batch_callable(my_path)

        return failures

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