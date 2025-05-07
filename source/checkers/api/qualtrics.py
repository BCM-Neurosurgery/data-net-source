from source.checkers.api.base import BaseAPIChecker
import json
import requests
import pandas as pd
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone
import os
import time

class QualtricsAPICheckerMixin(BaseAPIChecker):
    checker_name = "QualtricsAPIChecker"
    surveys_to_skip = [
    'TEST'
    ]


    def clean(self):
        pass

    def save(self, completed):
        pass

    def start_response_export(self, token, survey_id, startDate='1970-01-01T01:00:00Z'):
        '''
        Starts downloading survey response data
        '''


        url = f'https://iad1.qualtrics.com/API/v3/surveys/{survey_id}/export-responses/'
        header = {'X-API-TOKEN': token, "content-type": "application/json"}
        data = {'format':'csv', 'compress':False, 'sortByLastModifiedDate':True, 'startDate': startDate} 
        print(startDate)
        response = requests.post(url, json=data, headers=header)
        responsedata = response.json()
        print(responsedata)
        progressId = responsedata['result']['progressId'] # need to fix when there is no 'result'

        return progressId
    
    def check_response_export(self, token, survey_id, progressId):
        url = f'https://iad1.qualtrics.com/API/v3/surveys/{survey_id}/export-responses/{progressId}'
        headers = {'X-API-TOKEN': token}

        status = 'inProgress'
        data = None  # default in case of failure

        while status == 'inProgress':
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # will raise an HTTPError for bad status codes
            data = response.json()
            status = data['result']['status']
            time.sleep(2)

        if status == 'complete':
            fileId = data['result']['fileId']
            return fileId

        raise RuntimeError(f"Export failed or did not complete. Final status: {status}")
    
    def download_response_export(self, token, survey_id, fileId):
        url = f'https://iad1.qualtrics.com/API/v3/surveys/{survey_id}/export-responses/{fileId}/file'
        headers = {'X-API-TOKEN': token}

        response = requests.get(url, headers=headers)
        response.raise_for_status()  # raises an error if the request failed

        data = response.content.decode('utf-8')
        return data
    
    def check(self):
        '''
        1. get survey + patient data from config file
        2. export new survey responses based on logged data (date of last log if exists)
        3. save in directory specified in toml file (e.g. [patient]/[month_year]/[surveyname_datetime].csv)
        '''
    
        # log file import
        logs = self.load_state()
        logs_success = logs['success']
        # pull last response date/time from log file
        last_run_time = logs_success[-1]['time_of_run'] if (len(logs['success']) > 0) else '1970-01-01T01:00:00Z'
        print(last_run_time)

        # surveys to skip (from toml config file)
        surveys_to_skip = self.surveys_to_skip

        # config json data import
        with open(self.source_location['qualtrics_config'], 'r') as file:
            config = json.load(file)
        
        token = config['token'] # api token
        patient_ids = config['patient_ids'] # dict of patients and qualtrics IDs
        patient_contact_ids = config['patient_contact_ids']
        survey_ids = config["survey_ids"] # dict of survey IDs

        # pull and save new data by survey (patient/month_year/surveyname_datetime.csv)
        tasks = []
        failures = []
        for survey_name, survey_id in survey_ids.items():
            if survey_name not in surveys_to_skip:
                # Download all new responses to survey
                try:
                    progressId = self.start_response_export(token, survey_id, startDate=last_run_time)
                    fileId = self.check_response_export(token, survey_id, progressId)
                    data = self.download_response_export(token, survey_id, fileId)
                except Exception as e:
                    failure = {
                        'survey': survey_name,
                        'time_of_run': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        "error": str(e)
                    }
                    failures.append(failure)
                    logs['failure'].append(failure)
                else:

                    # convert raw csv of responses to df
                    csv_buffer = StringIO(data)
                    df = pd.read_csv(csv_buffer, skiprows=[2])
                    meta_df = df.iloc[0].to_frame().T
                    df = df.drop(df.index[0])
                    # iterate over df rows (responses), save each response based on patient ID (found through contactID) and datetime
                    for idx, row in df.iterrows():
                        if idx > 0:
                            contact_id = row['ContactID']
                            # Parse date info from 'EndDate'.
                            if 'InputDate' in row and pd.notna(row['InputDate']):
                                endDate = pd.to_datetime(row['InputDate']) # if there is a manual input date in the survey, then that overrides the normal date (which is then assumed to be the response date)
                            else:
                                endDate = pd.to_datetime(row['EndDate'])
                            year = endDate.year
                            date_str = endDate.strftime('%Y-%m-%d')

                            # Compose filename
                            filename = f"{survey_name}_{date_str}_{row['ResponseId']}.csv"
                            
                            # Create full directory path
                            output_dir = Path(self.source_location['path']) / patient_contact_ids[contact_id] / survey_name / str(year)
                            output_dir.mkdir(parents=True, exist_ok=True)
                            out_file = os.path.join(
                                output_dir, 
                                filename
                            )
                            
                            # Save the single-row DataFrame
                            row_df = row.to_frame().T  # Convert Series to DataFrame
                            combined_df = pd.concat([meta_df, row_df], ignore_index=True)
                            combined_df.to_csv(out_file, index=False)
                            print('Saved data in ',output_dir,' --- Date: ',date_str)

                            tasks.append(out_file)

                    # log last response time
                    df['EndDate'] = pd.to_datetime(df['EndDate'])
                    new_last_response_time = df['EndDate'].max()
                    state = {
                        'survey': survey_name,
                        'time_of_run': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'last_response_time': new_last_response_time
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

