# source/checkers/local_to_s3.py

import os
import json
import copy
from datetime import datetime
from .base import BaseChecker
from source.common import EMPTY_LOG
import logging

class StreamedFileCheckerMixin(BaseChecker):
    """
    A Checker mixin that finds new or modified files and empty directories.
    It compares items against a state log based on their modification times.
    """
    @property
    def checker_name(self):
        """
        Provides a user-friendly name for this checker.
        """
        return "StreamedFileChecker"

    def check(self) -> dict:
        """
        Walks a local directory, finds files and empty directories that are new
        or have been modified since the last run, and returns them as tasks.
        """
        source_path = self.source_location.get('path')
        if not source_path:
            raise ValueError("Source path must be specified in the config for local checker.")

        self.info(f"Starting check on directory: {source_path}")
        non_failure_events = self.load_non_failure()

        # Build a dictionary of processed items for quick lookup.
        # Key: file or directory path, Value: last modified timestamp.
        processed_items = {}
        for event in non_failure_events:
            filepath = event.get('filename') or event.get('uploaded')
            if filepath and 'modified' in event:
                processed_items[filepath] = event['modified']
        
        self.debug(f"Loaded {len(processed_items)} previously processed items from state.")
        new_items_to_do = []
        
        # Walk through all directories and files in the source path.
        for dirpath, dirnames, filenames in os.walk(source_path):
            # First, process all files in the current directory.
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                self.debug(f"Discovered file: {full_path}")
                
                try:
                    last_modified = os.path.getmtime(full_path)
                    
                    if full_path in processed_items:
                        self.debug(f"  - Found in state. Stored mod time: {processed_items[full_path]}, Current mod time: {last_modified}")
                        if processed_items[full_path] >= last_modified:
                            self.debug("  - Skipping: File is not modified.")
                            continue
                        else:
                            self.info(f"  - Found modified file, adding to tasks: {full_path}")
                    else:
                        self.info(f"  - Not found in state. Adding as a new task: {full_path}")

                    new_items_to_do.append(full_path)

                except FileNotFoundError:
                    self.warning(f"File {full_path} found during walk but could not be accessed.")
                    continue
            
            # An empty directory:
            # subdirectories (dirnames is empty) and no files (filenames is empty).
            if not filenames and not dirnames:
                self.debug(f"Discovered empty directory: {dirpath}")
                try:
                    last_modified = os.path.getmtime(dirpath)

                    if dirpath in processed_items:
                        self.debug(f"  - Found in state. Stored mod time: {processed_items[dirpath]}, Current mod time: {last_modified}")
                        if processed_items[dirpath] >= last_modified:
                            self.debug("  - Skipping: Directory is not modified.")
                            continue
                        else:
                            self.info(f"  - Found modified empty directory, adding to tasks: {dirpath}")
                    else:
                        self.info(f"  - Not found in state. Adding as a new task: {dirpath}")
                    
                    new_items_to_do.append(dirpath)

                except FileNotFoundError:
                    self.warning(f"Directory {dirpath} found during walk but could not be accessed.")
                    continue
        
        self.info(f"Check complete. Found {len(new_items_to_do)} new/modified items.")
        return {'to do': new_items_to_do, 'failure': []}

    def save(self, completed: dict):
        """
        Updates the state file with the modification times of successfully processed files and directories.
        """
        state_data = self.load_state()

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

    def clean(self):
        """
        Cleans the state file. This checker does not create temporary files,
        so it only needs to manage its state log.
        """
        self.info("Cleaning state file...")
        current_state = self.load_state()
        cleaned_state = self.clean_outdated(current_state)
        self.write_state(cleaned_state)
        self.info("State file cleaned.")
