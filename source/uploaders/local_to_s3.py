# source/uploaders/local_to_s3.py

import boto3
import os
from datetime import datetime
from .base import RemoteFilesystemUploader
import logging

class S3UploaderMixin(RemoteFilesystemUploader):
    """
    An Uploader that uploads files and directories to an AWS S3 bucket,
    following the structure of the RemoteFilesystemUploader base class.
    This version avoids a custom __init__ method.
    """
    s3_client = None

    @property
    def uploader_name(self):
        """Provides a user-friendly name for this uploader."""
        return "S3Uploader"

    def make_connection(self):
        """Establishes a connection to S3 by creating a boto3 client."""
        self.info("Creating S3 client...")
        if not self.target_location.get('bucket'):
            raise ValueError("Target S3 bucket not specified in config.")
        self.s3_client = boto3.client('s3')
        self.info("S3 client created successfully.")

    def close_connection(self):
        """Cleans up the S3 client. Boto3 handles connection pooling automatically."""
        self.info("S3 connection is managed by boto3; no explicit close needed.")
        self.s3_client = None

    def check_exists(self, target_file: str) -> bool:
        """
        Checks if an object already exists in the S3 bucket.
        'target_file' here is the S3 object key.
        """
        bucket = self.target_location.get('bucket')
        try:
            self.s3_client.head_object(Bucket=bucket, Key=target_file)
            return True
        except self.s3_client.exceptions.ClientError as e:
            # A 404 Not Found error means the object does not exist.
            if e.response['Error']['Code'] == '404':
                return False
            else:
                # Re-raise any other client error.
                self.error(f"Error checking for object s3://{bucket}/{target_file}: {e}")
                raise

    def make_folders(self, target_directory: str):
        """
        Ensures a 'folder' exists in S3 by creating an empty object with a trailing slash.
        'target_directory' here is the S3 key for the directory.
        """
        bucket = self.target_location.get('bucket')
        # S3 folders are just empty objects with a key ending in '/'.
        # We only create it if it doesn't already exist to be idempotent.
        if not self.check_exists(target_directory):
            self.info(f"Creating empty directory in S3: s3://{bucket}/{target_directory}")
            self.s3_client.put_object(Bucket=bucket, Key=target_directory, Body='')

    def do_move(self, filename: str, destination: str):
        """
        Uploads a single file to the S3 bucket.
        'filename' is the local path, and 'destination' is the target S3 key.
        """
        bucket = self.target_location.get('bucket')
        self.info(f"Uploading file {filename} to s3://{bucket}/{destination}")
        # We can use the time_upload wrapper from the base class for performance metrics.
        return self.time_upload(
            self.s3_client.upload_file,
            filename,
            bucket,
            destination
        )

    def upload(self, ready: dict) -> dict:
        """
        The core upload method orchestrator.
        Note: We override the base 'upload' method because S3 has a distinction
        between files and directories that the generic FileSystemUploader.upload()
        doesn't account for. This implementation preserves that logic while still
        using the abstracted helper methods.
        """
        self.info("S3Uploader 'upload' method started.")
        self.make_connection()
        
        successes = []
        failures = ready.get("failure", [])
        # Adding skipped list to stick to the format
        skipped = []
        items_to_process = ready.get('to upload', [])
        bucket = self.target_location.get('bucket')
        target_prefix = self.target_location.get('prefix', '')

        try:
            for local_path in items_to_process:
                try:
                    # Construct the S3 object key directly within the loop.
                    relative_path = self.raw_relative_filepath(local_path)
                    if target_prefix:
                        s3_key = os.path.join(target_prefix.rstrip('/'), relative_path).replace('\\', '/')
                    else:
                        s3_key = relative_path.replace('\\', '/')

                    destination_uri = f"s3://{bucket}/{s3_key}"

                    if os.path.isfile(local_path):
                        # Handle file upload
                        if not self.target_location.get('allow-overwrite', False) and self.check_exists(s3_key):
                            self.warning(f"Skipping existing file: {destination_uri}")
                            # Create a record for the skipped file 
                            skip_record = {
                                "type": "RemoteFileExists",
                                "filename": local_path,
                                "destination": destination_uri,
                                "timestamp": datetime.utcnow().timestamp()
                            }
                            skipped.append(skip_record)
                            continue
                        
                        self.do_move(local_path, s3_key)
                    
                    elif os.path.isdir(local_path):
                        # Handle directory creation
                        s3_key_dir = f"{s3_key.rstrip('/')}/"
                        self.make_folders(s3_key_dir)
                    
                    else:
                        self.warning(f"Skipping item that is not a file or directory: {local_path}")
                        continue
                    
                    success_record = {
                        "type": "upload success",
                        "filename": local_path,
                        "destination": destination_uri,
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
        finally:
            self.close_connection()
        self.info(f"S3Uploader 'upload' method finished. Success: {len(successes)}, Failure: {len(failures)}, Skipped: {len(skipped)}")
        return {'success': successes, 'failure': failures, 'skipped': skipped}