import boto3
import os
import json
import copy
import shutil # Import the shutil module for directory operations
from datetime import datetime
from .base import BaseChecker   # Imports the abstract base class for checkers
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
    # Using a class variable to map local paths to S3 details.
    s3_file_map = {}

    @property
    def checker_name(self):
        """
        Provides a user-friendly name for this checker.
        """
        return "S3ObjectChecker"

    def check(self) -> dict:
        """
        The core method of the checker. It lists objects in the source S3 bucket,
        compares them against the state loaded via `self.load_state()`, downloads
        any new objects, and returns a dictionary of tasks for the next pipeline step.
        """
        s3_client = boto3.client('s3')
        
        source_bucket = self.source_location.get('bucket')
        source_prefix = self.source_location.get('prefix', '')
        temp_dir = self.source_location.get('path')

        if not source_bucket or not temp_dir:
            raise ValueError("Source bucket and middle path must be specified in the config.")

        os.makedirs(temp_dir, exist_ok=True)
        
        # Use the base class's helper to get a list of all successful or skipped events.
        # This will now raise a FileNotFoundError if the state file does not exist.
        non_failure_events = self.load_non_failure()

        # To easily check for processed files, create a dictionary mapping the S3 object key
        # to its last known ETag.
        processed_objects = {}
        for event in non_failure_events:
            if 's3_key' in event and 'etag' in event:
                processed_objects[event['s3_key']] = event['etag']
        
        # Prepare lists to hold the results of the check.
        new_local_files = []
        download_failures = []

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

                    # Construct the full local path, mirroring the S3 object key.
                    # We must first remove the source prefix from the key.
                    relative_path = os.path.relpath(object_key, source_prefix)
                    local_file_path = os.path.join(temp_dir, relative_path)
                    
                    try:
                        # Ensure the local parent directory for the file exists before downloading.
                        local_parent_dir = os.path.dirname(local_file_path)
                        os.makedirs(local_parent_dir, exist_ok=True)

                        self.info(f"New S3 object found: {object_key}. Downloading...")
                        # Download the new file to the temporary local directory.
                        s3_client.download_file(source_bucket, object_key, local_file_path)
                        
                        # If download succeeds, map the local path back to its S3 details.
                        self.s3_file_map[local_file_path] = {"key": object_key, "etag": object_etag}
                        new_local_files.append(local_file_path)

                    except Exception as e:
                        self.error(f"Failed to download {object_key}: {e}")
                        download_failures.append({"file": object_key, "error": str(e)})

        except Exception as e:
            self.error(f"A critical error occurred while checking for files in S3 bucket {source_bucket}: {e}")
            # Re-raising the exception to allow the main process() function to handle the failure.
            raise e

        return {'to do': new_local_files, 'failure': download_failures}

    def save(self, completed: dict):
        """
        Updates the state file by adding new entries for successfully processed
        and failed tasks, conforming to the structure required by BaseChecker.
        """
        # Load the current state; this will fail if the file doesn't exist.
        state_data = self.load_state()

        # Iterate through the success records returned by the uploader.
        for success_record in completed.get('success', []):
            # The uploader returns a dictionary; extract the original local file path.
            local_path = success_record.get('filename')

            # Check if this path is one that our checker downloaded.
            if local_path and local_path in self.s3_file_map:
                s3_details = self.s3_file_map[local_path]
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
        Performs all cleanup actions:
        1. Deletes the entire temporary local directory that was used for downloads.
        2. Cleans the state file using the helper methods from BaseChecker.
        """
        self.info("Cleaning up temporary download directory.")
        # Get the path to the temporary directory from the configuration.
        temp_dir = self.source_location.get('path')
        if temp_dir and os.path.isdir(temp_dir):
            try:
                # Use shutil.rmtree to recursively delete the entire directory.
                shutil.rmtree(temp_dir)
                self.info(f"Successfully removed temporary directory: {temp_dir}")
            except OSError as e:
                self.error(f"Error removing temporary directory {temp_dir}: {e}")
        
        # Clear the map after use.
        self.s3_file_map.clear()
        
        # State File Cleanup Logic
        self.info("Cleaning state file...")
        current_state = self.load_state()
        cleaned_state = self.clean_outdated(current_state)
        self.write_state(cleaned_state)
        self.info("State file cleaned.")

