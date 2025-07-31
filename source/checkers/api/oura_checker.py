# import configuration here 
from source.checkers.base import BaseChecker
import json
import requests
from datetime import datetime
from pathlib import Path
from paramiko import SSHClient 

class OuraCheckerMixin(BaseChecker):
    checker_name = "OuraChecker"
    # delete_age_hours = 24

    def make_connection(self): 
        self.source = self.source_location
        self.info("Connecting to remote SSH and setting up paths...")       
        self.state_path = Path(self.state_path)
        self.source_data_path = Path(self.source["source_data_path"])
        self.webhook_post_path = Path(self.source["webhook_post_path"])
        self.data_net_path = Path(self.source["data_net_path"])
        self.ssh_config = self.source.get("ssh_config", None)
        self.sftp = None

        
        # Set up the ssh client
        if self.ssh_config is not None: 
            self.ssh = SSHClient()
            self.ssh.load_system_host_keys()
            self.ssh.connect(hostname=self.ssh_config["hostname"], 
                             username=self.ssh_config["username"], 
                             key_filename = self.ssh_config["key_filename"])
            self.sftp = self.ssh.open_sftp()
        
    # reads json file remotely via SSH
    def _read_json_file(self, path):
        if self.ssh_config:
            with self.sftp.open(path, "r") as f:
                return json.load(f)
        raise FileNotFoundError("json file not found")
        

    def _map_user_to_participant(self, user_id):
        map_path = self.source_data_path / "participant_map.json"
        
        try:
            with self.sftp.open(str(map_path), "r") as f:
                user_map = json.load(f)
        except IOError:
            raise FileNotFoundError("Could not find participant_map.json")
    
        self.info(f"User ID: {user_id}, mapped participant: {user_map.get(user_id)}")
        return user_map.get(user_id)

    # find new webhook posts that haven't been processed and query the api for the data 
    def check(self):
        if not hasattr(self, "sftp"):
            self.make_connection()

        # get the upload state
        if not self.state_path.exists():
            self.info("Local upload_state.json not found, creating new one")
            state = {"success": [], "failure": [], "skipped": []}
            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)
        else:
            with open(self.state_path, "r") as f:
                state = json.load(f)
        
        self.upload_state = state

        # pass the state variables from function to function -> potentially avoiding self.?
        to_process = []
        failures = []

        # Load tokens
        token_path = self.source_data_path / "oura_tokens.json"
        tokens = self._read_json_file(str(token_path))

        if self.sftp:
            user_dirs = self.sftp.listdir(str(self.webhook_post_path))
            self.info(f"Users found in webhook dir:  {user_dirs}")
            for user in user_dirs:
                user_path = f"{self.webhook_post_path}/{user}"
                modality_dirs = self.sftp.listdir(str(user_path))
                for modality in modality_dirs:
                    modality_path = f"{user_path}/{modality}"
                    for filename in self.sftp.listdir(str(modality_path)):
                        if not filename.endswith(".json"):
                            continue
                        file_path = f"{modality_path}/{filename}"
                        try:
                            payload = self._read_json_file(str(file_path))
                            result = self._handle_payload(payload, tokens, filename)
                            if isinstance(result, dict) and all(k in result for k in ("key", "uploaded", "timestamp")):
                                to_process.append(result)
                            else:
                                if result is not None:
                                    failures.append({
                                        "file": file_path,
                                        "error": f"Malformed result returned: {result}",
                                        "timestamp": datetime.now().timestamp()
                                    })
                        except Exception as e:
                            self.info(f"[ERROR] Failed on {file_path}: {str(e)}")
                            failures.append({
                                "file": file_path,
                                "error": str(e),
                                "timestamp": datetime.now().timestamp()
                            })
        if to_process and failures:
            self.info(f"To process: {to_process[0]}")
            self.info(f"Failures: {failures[0]}")
        return {"to do": to_process, "failure": failures}

    def _handle_payload(self, payload, tokens, timestamp_clean):
        data_type = payload["data_type"]
        user_id = payload["user_id"]
        object_id = payload["object_id"]

        participant_id = self._map_user_to_participant(user_id)
        if not participant_id:
            return

        key = f"{participant_id}/{data_type}/{timestamp_clean}"

        #need to correctly mark successful uploads only here

        token = tokens.get(participant_id, {}).get("access_token")
        if not token:
            self.info(f"Skipping, no token for {participant_id}")
            return

        url = f"https://api.ouraring.com/v2/usercollection/{data_type}/{object_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)
        self.info(f"Queried {url} for {participant_id}/{data_type}: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        dest_dir = self.data_net_path / participant_id / data_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / timestamp_clean

        with open(dest_file, "w") as f:
            f.write(json.dumps(data, indent=2))

            return {
                "key": key,
                "uploaded": str(dest_file),
                "timestamp": datetime.now().timestamp()
            }

    def save(self, completed):
        if not hasattr(self, "sftp"):
            self.make_connection()
        to_save = completed.get("success", [])
        if to_save:
            self.info(f"[Save] to_save contents: {to_save[0]}") 

        self.info(f"[Save] Marking {len(to_save)} files as uploaded")

        for item in to_save:
            self.upload_state["success"].append({
                "key": item["key"],
                "uploaded": item["uploaded"],
                "timestamp": item["timestamp"]
            })

        # write once after all are added
        with open(self.state_path, "w") as f:
            json.dump(self.upload_state, f, indent=2)

    def clean(self):
        if not hasattr(self, "sftp"):
            self.make_connection()
        with open(self.state_path, "r") as f:
            self.upload_state = json.load(f)
        
        # clean outdated log entries
        cleaned_log = super().clean_outdated(self.upload_state)

        # delete old uploaded files
        final_log = super().clean_old_success(cleaned_log)

        # save cleaned upload log
        with open(self.state_path, "w") as f:
            json.dump(final_log, f, indent=2)

