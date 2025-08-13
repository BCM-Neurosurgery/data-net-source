# source/checkers/local_to_s3.py

# Import the existing FileCheckerMixin to reuse its file-scanning logic.
from source.checkers.local import FileCheckerMixin
import os
import json
import copy
from datetime import datetime
from source.common import EMPTY_LOG
import logging

class LocalToS3Checker(FileCheckerMixin):
    """
    This is the checker for the Local-to-S3 pipeline.

    It inherits all of its core file-checking functionality from the existing
    FileCheckerMixin. Its only job is to provide a complete and robust
    implementation of the `save` method.

    """
    @property
    def checker_name(self):
        """
        Provides a user-friendly name for this specific checker.
        """
        return "LocalToS3Checker"

    # The `check` and `clean` methods are now fully inherited from the
    # parent FileCheckerMixin.

    def save(self, completed: dict):
        """
        Provides a complete implementation for updating the state file with the
        modification times of successfully processed files.
        """
        try:
            state_data = self.load_state()
        except (FileNotFoundError, json.JSONDecodeError):
            state_data = copy.deepcopy(EMPTY_LOG)

        for success_record in completed.get('success', []):
            local_path = success_record.get('filename')
            if local_path and os.path.exists(local_path):
                success_event = {
                    "timestamp": datetime.utcnow().timestamp(),
                    "filename": local_path,
                    "modified": os.path.getmtime(local_path),
                    "destination": success_record.get('destination')
                }
                state_data['success'].append(success_event)

        for failure_info in completed.get('failure', []):
            state_data['failure'].append({
                "timestamp": datetime.utcnow().timestamp(),
                **failure_info
            })

        self.write_state(state_data)
        self.info(f"Saved state for {len(completed.get('success',[]))} successes and {len(completed.get('failure',[]))} failures.")

