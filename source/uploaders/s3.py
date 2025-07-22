import boto3
import os
from datetime import datetime
from .base import BaseUploader
import logging

class S3UploaderMixin(BaseUploader):
    """
    A mixin class for uploading files to an AWS S3 bucket.

    This uploader:
    1. Takes a list of local file paths ready for processing.
    2. Uploads each file to a specified AWS S3 destination bucket and prefix.
    3. Reliably returns a dictionary detailing the successes and failures, as required
       by the main processing loop.
    """
    @property
    def uploader_name(self):
        """
        Provides a user-friendly name for this uploader.
        """
        return "S3Uploader"

    def upload(self, ready: dict) -> dict:
        """
        The core method of the uploader. Receives a dictionary of tasks,
        uploads each file to the target S3 bucket, and returns a dictionary
        detailing the results.
        """
        self.info("S3Uploader 'upload' method started.")
        # The framework passes a dictionary; we get the list of files from the 'to upload' key.
        files_to_process = ready.get('to upload', [])

        s3_client = boto3.client('s3')
        # Retrieve the destination S3 bucket and prefix from the configuration.
        target_bucket = self.target_location.get('bucket')
        target_prefix = self.target_location.get('prefix', '')

        if not target_bucket:
            self.error("Target S3 bucket not specified in config. Aborting upload.")
            # Return a valid dictionary even on configuration error.
            return {'success': [], 'failure': [{"error": "Target bucket not configured"}]}

        # Prepare lists to report the results, conforming to the base class standard.
        successes = []
        failures = ready.get("failure", []) # Pass through any failures from previous steps

        for local_file_path in files_to_process:
            try:
                # Get just the filename from the full temporary path.
                file_name = os.path.basename(local_file_path)
                
                # Construct the full S3 object key for the destination. This logic
                # correctly handles cases where the prefix is empty or already has a slash.
                if target_prefix:
                    s3_key = f"{target_prefix.rstrip('/')}/{file_name}"
                else:
                    s3_key = file_name

                self.info(f"Uploading {local_file_path} to s3://{target_bucket}/{s3_key}")
                # Perform the actual upload. Boto3 handles large files automatically.
                s3_client.upload_file(local_file_path, target_bucket, s3_key)
                
                # Create a success record in the format expected by the framework's save() method.
                success_record = {
                    "type": "upload success",
                    "filename": local_file_path,
                    "destination": f"s3://{target_bucket}/{s3_key}",
                    "timestamp": datetime.utcnow().timestamp()
                }
                successes.append(success_record)

            except Exception as e:
                # If any error occurs, log it and create a detailed failure record.
                self.error(f"Failed to upload {local_file_path} to S3: {e}")
                failure_record = {
                    "type": "upload failure",
                    "filename": local_file_path,
                    "error": str(e),
                    "timestamp": datetime.utcnow().timestamp()
                }
                failures.append(failure_record)

        self.info(f"S3Uploader 'upload' method finished. Success: {len(successes)}, Failure: {len(failures)}")
        # Always return a dictionary in the format expected by the framework's `process()` method.
        return {'success': successes, 'failure': failures}

    def clean(self):
        
        pass
