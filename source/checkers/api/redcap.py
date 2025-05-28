from source.checkers.api.base import BaseAPIChecker
import json
import requests
import pandas as pd
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone
import os
import time
import shutil

class RedcapAPICheckerMixin(BaseAPIChecker):
    checker_name = "RedcapAPIChecker"
    
    def clean(self):
        path = self.source_location['path']
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)  # remove file or symlink
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)  # remove directory
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
        pass

    def save(self, completed):
        pass
    
    def check(self):
        '''
        1. get redcap IDs from json config file
        2. API call by patient, download all data
        3. Save state as latest date per patient (per survey?)
        4. If new survey data since date overwrite with new data
        '''
        REDCap_URL = 'https://redcap.research.bcm.edu/redcap/api/'

        # log file import
        logs = self.load_state()
        logs_success_df = pd.DataFrame(logs['success'])

        # config json data import
        with open(self.source_location['redcap_config'], 'r') as file:
            config = json.load(file)

        token = config['token'] # api token
        redcap_ids = config[self.study_id]
        
        tasks = []
        failures = []
        for patient_id, redcap_id in redcap_ids.items():
            try:
                data = {
                    'token': token,
                    'content': 'record',
                    'action': 'export',
                    'format': 'csv',
                    'type': 'flat',
                    'csvDelimiter': '',

                    'records[0]': redcap_ids[patient_id],

                    'rawOrLabel': 'raw',
                    'rawOrLabelHeaders': 'raw',
                    'exportCheckboxLabel': 'false',
                    'exportSurveyFields': 'true',
                    'exportDataAccessGroups': 'false',
                    'returnFormat': 'json'
                }
                r = requests.post(REDCap_URL, data=data, verify=False) # download patient data
            except Exception as e:
                failure = {
                    'patient': patient_id,
                    'time_of_run': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "error": str(e)
                }
                failures.append(failure)
                logs['failure'].append(failure)
            else:
                # for each survey, compare maximum date in state file to new maximum
                df = pd.read_csv(StringIO(r.text))
                df['all_dates'] = df['date'].fillna(df['date_2']).fillna(df['intervention_date'])
                df['all_dates'] = pd.to_datetime(df['all_dates'], format='%Y-%m-%d')
                df_dates = df['all_dates'].dropna()

                log_dates = pd.Series(dtype='datetime64[ns]')  # default empty

                required_cols = {'patient', 'last_date'}
                if required_cols.issubset(logs_success_df.columns):
                    log_dates = logs_success_df[logs_success_df['patient'] == patient_id]['last_date'].dropna()
                    log_dates = pd.to_datetime(log_dates)

                # fallback if log_dates is empty
                max_log_date = log_dates.max() if not log_dates.empty else pd.NaT
                max_df_date = df_dates.max() if not df_dates.empty else pd.NaT

                if max_df_date != max_log_date:
                    self.log(f'New dates for {patient_id}')

                    # Compose filename
                    filename = f"{patient_id}_redcap_raw.csv"
                    
                    output_dir = Path(self.source_location['path']) / patient_id / 'redcap'
                    output_dir.mkdir(parents=True, exist_ok=True)
                    for _, row in df.iterrows():
                        event = row['redcap_event_name']
                        filename = f"{patient_id}_{event}_redcap_raw.csv"
                        out_file = output_dir / filename

                        # Save the single-row DataFrame
                        pd.DataFrame([row]).to_csv(out_file, index=False)
                        tasks.append(str(out_file))
                                        
                    state = {
                        'patient': patient_id,
                        'time_of_run': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'last_date': max_df_date
                    }
                    logs['success'].append(state)

        # Convert datetime objects in _state to ISO format before saving
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()  # Convert datetime to string
            raise TypeError(f"Type {type(obj)} not serializable")

        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(logs, log, indent=2, default=convert_datetime) 


        return {'to do': tasks, 'failure': failures}

