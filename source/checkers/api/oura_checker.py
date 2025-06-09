# import configuration here 
from source.checkers.base import BaseChecker
from pathlib import Path
import shutil
import json
import requests

class OuraChecker(BaseChecker):
    checker_name = "oura_checker"
    def __init__(self, source_data_path, upload_state_path, webhook_post_path, *args, **kwargs):
        super().__init__(source_data_path, upload_state_path, *args, **kwargs)  #just in case base adds an init 
        self.source_data_path = Path(source_data_path)
        self.upload_state_path = Path(upload_state_path)
        self.webhook_post_path = Path(webhook_post_path)
        self.uploaded = self._load_upload_state()

    # load the state path for a memory of previously uploaded files    
    def _load_upload_state(self):
        if self.upload_state_path.exists():
            with open(self.upload_state_path, "r") as f:
                return json.load(f)
        return {}   # return a dict even if it's empty

    # update the record of what's been processed
    def _mark_uploaded(self, participant_id, data_type, timestamp):
        key = f"{participant_id}/{data_type}/{timestamp}"
        self.uploaded[key] = True
        with open(self.upload_state_path, "w") as f:
            json.dump(self.uploaded, f, indent=2)


    # find new webhook posts that haven't been processed 
    def check(self):
        self.to_process = []
        failures = []

        for user_dir in self.webhook_post_path.iterdir():
            for modality_dir in user_dir.iterdir():
                for file in modality_dir.glob("*.json"):
                    try:
                        with open(file, "r") as f:
                            payload = json.load(f)
                        
                        data_type = payload["data_type"]
                        user_id = payload["user_id"]

                        #clean event time file name
                        event_time = payload["event_time"]  # oura event time
                        timestamp_clean = file.stem  # uses the filename from the listener (time it was received)

                        participant_id = self._map_user_to_participant(user_id)
                        if not participant_id:
                            continue
                        key = f"{participant_id}/{data_type}/{timestamp_clean}"
                        if key not in self.uploaded:
                            self.to_process.append((file, participant_id, data_type, event_time, timestamp_clean))
                    except Exception as e:
                        failures.append((file, str(e)))
        return {
            "to do": self.to_process,
            "failure": failures
        }
        
    # save the webhook posts that haven't been processed yet
    def save(self, dict_completed_tasks=None):
        
        # load the tokens
        token_path = self.source_data_path / "oura_tokens.json"
        
        if not token_path.exists():
            raise FileNotFoundError("Token file not found in oura_data/")
        
        with open(token_path, "r") as f:
            tokens = json.load(f)
            
        for file, participant_id, data_type, event_time, timestamp_clean in self.to_process:
            token = tokens.get(participant_id, {}).get("access_token")
            if not token:
                print(f"Skipping, no token found for {participant_id}")
                continue
            date = event_time.split("T")[0]

            # oura api request
            url = f"https://api.ouraring.com/v2/usercollection/{data_type}"
            headers = {"Authorization": f"Bearer {token}"}
            params = {"start_date": date, "end_date": date}

            # make the request
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status() # raise an error if the response is not 200 OK
                data = response.json()
            except Exception as e:
                print(f"Could not fetch Oura data for {participant_id}, {data_type}, {date}: {e}")
                continue

            dest_dir = self.source_data_path / participant_id / data_type
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_file = dest_dir / f"{timestamp_clean}.json"
            with open(dest_file, "w") as f:
                json.dump(data, f, indent=2)

            self._mark_uploaded(participant_id=participant_id, data_type=data_type, timestamp=event_time)



    def clean(self, dict_completed_tasks=None):
        num_deleted = 0

        for user_dir in self.webhook_post_path.iterdir():
            for modality_dir in user_dir.iterdir():
                for file in modality_dir.glob("*.json"):
                    try:
                        with open(file, "r") as f:
                            payload = json.load(f)
                            
                        data_type = payload["data_type"]
                        user_id = payload["user_id"]
                        timestamp_clean = file.stem  # gets '2025-06-08T09-14-57' if that's the filename

                        participant_id = self._map_user_to_participant(user_id)
                        if not participant_id: 
                            continue
                        key = f"{participant_id}/{data_type}/{timestamp_clean}"
                        if key in self.uploaded:
                            file.unlink()  # Permanently delete the file
                            num_deleted += 1

                    except Exception as e:
                        print(f"[Clean Error] Could not process {file.name}: {e}")

        print(f"[Clean] Deleted {num_deleted} processed webhook files.")

    def _map_user_to_participant(self, user_id):
        map_path = self.source_data_path / "participant_map.json"
        if not map_path.exists():
            print("Could not find participant_map.json")
            return None
        
        with open(map_path, "r") as f:
            user_map= json.load(f)
        
        return user_map.get(user_id)

    
