# source/uploaders/local_to_s3.py

import boto3
import os
from datetime import datetime
from .base import BaseUploader
import logging

class S3UploaderMixin(BaseUploader):
    """
    An Uploader mixin that uploads both files and empty directories to S3,
    preserving the relative directory structure from the source folder.
    """
    @property
    def uploader_name(self):
        """
        Provides a user-friendly name for this uploader.
        """
        return "S3Uploader"

    def upload(self, ready: dict) -> dict:
        """
        The core method of the uploader. It processes a list of local paths,
        uploading files and creating empty directories in the target S3 bucket.
        """
        self.info("S3Uploader 'upload' method started.")
        items_to_process = ready.get('to upload', [])

        s3_client = boto3.client('s3')
        target_bucket = self.target_location.get('bucket')
        target_prefix = self.target_location.get('prefix', '')

        if not target_bucket:
            self.error("Target S3 bucket not specified in config. Aborting upload.")
            return {'success': [], 'failure': [{"error": "Target bucket not configured"}]}

        successes = []
        failures = ready.get("failure", [])

        for local_path in items_to_process:
            try:
                # Use the base class's helper to get the item's path relative to the source.
                relative_path = self.raw_relative_filepath(local_path)
                
                # Construct the final S3 key.
                if target_prefix:
                    s3_key = os.path.join(target_prefix.rstrip('/'), relative_path).replace('\\', '/')
                else:
                    s3_key = relative_path.replace('\\', '/')

                # Logic to differentiate between files and directories ---
                if os.path.isfile(local_path):
                    # This is a file, use the standard upload_file method.
                    self.info(f"Uploading file {local_path} to s3://{target_bucket}/{s3_key}")
                    s3_client.upload_file(local_path, target_bucket, s3_key)
                elif os.path.isdir(local_path):
                    # This is a directory. To create it in S3, we upload an empty
                    # object with a key that ends in a slash.
                    s3_key_dir = f"{s3_key.rstrip('/')}/"
                    self.info(f"Creating empty directory in S3: s3://{target_bucket}/{s3_key_dir}")
                    s3_client.put_object(Bucket=target_bucket, Key=s3_key_dir, Body='')
                else:
                    # If the path is neither a file nor a directory (e.g., a broken link), skip it.
                    self.warning(f"Skipping item that is not a file or directory: {local_path}")
                    continue
                
                success_record = {
                    "type": "upload success",
                    "filename": local_path,
                    "destination": f"s3://{target_bucket}/{s3_key}",
                    "timestamp": datetime.utcnow().timestamp()
                }
                successes.append(success_record)

            except Exception as e:
                self.error(f"Failed to process {local_path}: {e}")
                failure_record = {
                    "type": "upload failure",
                    "filename": local_path,
                    "error": str(e),
                    "timestamp": datetime.utcnow().timestamp()
                }
                failures.append(failure_record)

        self.info(f"S3Uploader 'upload' method finished. Success: {len(successes)}, Failure: {len(failures)}")
        return {'success': successes, 'failure': failures}


