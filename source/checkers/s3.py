import boto3
import os
import json
import copy
from datetime import datetime
from .base import BaseChecker  # Imports the abstract base class for checkers
from source.common import EMPTY_LOG # Imports the standard empty log structure
import logging

class S3ObjectCheckerMixin(BaseChecker):
    """A mixin class for checking and downloading new or updated objects from an AWS S3 bucket.
    
    This checker:
    1. Uses `self.load_state()` to read the record of previously processed files.
    2. Checks an AWS S3 bucket for new or updated objects.
    3. Downloads new objects to a local temporary directory, handling individual download errors.
    4. Implements a `save()` method that updates the state by adding new success/failure
       events in the format required by the base class.
    5. Implements a `clean()` method that uses the base class's `clean_outdated`
       helper to keep the state file tidy.
    """
    def __init__(self, **kwargs):
        # Always call the parent's constructor. This sets up self.state_path, etc.
        super().__init__(**kwargs)
        # A private dictionary to map local file paths back to their S3 details.
        # This is essential for the `save` method to create correctly formatted state entries.
        self._s3_file_map = {}

    @property
    def checker_name(self):
        """
        Provides a user-friendly name for this checker, satisfying the abstract property
        in the BaseChecker.
        """
        return "S3ObjectChecker"

    def check(self) -> dict:
        """
        The core method of the checker. It lists objects in the source S3 bucket,
        compares them against the state loaded via `self.load_state()`, downloads
        any new objects, and returns a dictionary of tasks for the next pipeline step.
        """
        s3_client = boto3.client('s3')
        
        # These attributes are set by ParserCommon and are used by the base class methods.
        source_bucket = self.source_location.get('bucket')
        source_prefix = self.source_location.get('prefix', '')
        temp_dir = self.middle_location.get('path')

        if not source_bucket or not temp_dir:
            raise ValueError("Source bucket and middle path must be specified in the config.")

        # Ensure the temporary directory for downloads exists.
        os.makedirs(temp_dir, exist_ok=True)
        
        # --- Conforming to BaseChecker: Use self.load_state() ---
        # Load the current state using the base class's method.
        try:
            current_state = self.load_state()
        except (FileNotFoundError, json.JSONDecodeError):
            # If the state file doesn't exist or is invalid, start with an empty one.
            self.info("State file not found or invalid, starting fresh.")
            current_state = copy.deepcopy(EMPTY_LOG)

        # To easily check for processed files, create a dictionary mapping the S3 object key
        # to its last known ETag. We look in both 'success' and 'skipped' lists.
        processed_objects = {}
        for event in current_state.get('success', []) + current_state.get('skipped', []):
            if 's3_key' in event and 'etag' in event:
                processed_objects[event['s3_key']] = event['etag']
        
        # Prepare lists to hold the results of the check.
        new_local_files = []
        download_failures = []
        self._s3_file_map.clear() # Clear the map for the current run

        try:
            # Use a paginator for efficiency, especially in buckets with many objects.
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=source_bucket, Prefix=source_prefix)

            for page in pages:
                for obj in page.get('Contents', []):
                    object_key = obj['Key']
                    object_etag = obj['ETag'].strip('"') # ETag can sometimes have quotes

                    # Ignore S3's representation of "folders".
                    if object_key.endswith('/'):
                        continue

                    # If this exact version of the file has been processed, skip it.
                    if processed_objects.get(object_key) == object_etag:
                        continue 

                    local_file_path = os.path.join(temp_dir, os.path.basename(object_key))
                    
                    try:
                        self.info(f"New S3 object found: {object_key}. Downloading...")
                        # Download the new file to the temporary local directory.
                        s3_client.download_file(source_bucket, object_key, local_file_path)
                        
                        # If download succeeds, map the local path back to its S3 details.
                        self._s3_file_map[local_file_path] = {"key": object_key, "etag": object_etag}
                        new_local_files.append(local_file_path)

                    except Exception as e:
                        # If a single download fails, log it and continue to the next file.
                        self.error(f"Failed to download {object_key}: {e}")
                        download_failures.append({"file": object_key, "error": str(e)})

        except Exception as e:
            self.error(f"A critical error occurred while checking for files in S3 bucket {source_bucket}: {e}")
            # On critical failure, return an empty 'to do' list.
            return {'to do': [], 'failure': [str(e)]}

        # Return the list of downloaded files and any download failures.
        return {'to do': new_local_files, 'failure': download_failures}

    def save(self, completed: dict):
        """
        Updates the state file by adding new entries for successfully processed
        and failed tasks, conforming to the structure required by BaseChecker.
        """
        try:
            state_data = self.load_state()
        except (FileNotFoundError, json.JSONDecodeError):
            state_data = copy.deepcopy(EMPTY_LOG)

        # Iterate through the success records returned by the uploader.
        for success_record in completed.get('success', []):
            # The uploader returns a dictionary; extract the original local file path.
            local_path = success_record.get('filename')
            
            # Check if this path is one that our checker downloaded.
            if local_path and local_path in self._s3_file_map:
                s3_details = self._s3_file_map[local_path]
                # Create a new, detailed success event for the state file.
                new_success_event = {
                    "timestamp": success_record.get('timestamp', datetime.utcnow().timestamp()),
                    "s3_key": s3_details['key'],
                    "etag": s3_details['etag'],
                    "uploaded": local_path,
                    "destination": success_record.get('destination')
                }
                state_data['success'].append(new_success_event)
        
        # Add any failures from the uploader to the state file as well.
        for failure_info in completed.get('failure', []):
            state_data['failure'].append({
                "timestamp": datetime.utcnow().timestamp(),
                **failure_info
            })

        # Use the base class's method to write the updated state to disk.
        self.write_state(state_data)
        self.info(f"Saved state for {len(completed.get('success',[]))} successes and {len(completed.get('failure',[]))} failures.")

    def clean(self):
        """
        Performs state file cleanup using the helper methods provided by BaseChecker.
        This keeps the state file from growing indefinitely.
        """
        self.info("Cleaning state file...")
        try:
            current_state = self.load_state()
            # Use the base class's helper to remove all but the most recent entry for each file.
            cleaned_state = self.clean_outdated(current_state)
            self.write_state(cleaned_state)
            self.info("State file cleaned.")
        except (FileNotFoundError, json.JSONDecodeError):
            self.warning("Could not clean state file because it does not exist or is invalid.")

