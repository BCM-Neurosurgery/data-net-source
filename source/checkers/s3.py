# The checker code for S3 bucket access goes here.

import boto3
import os
from .base import BaseChecker
import json
import logging

class S3ObjectCheckerMixin(BaseChecker):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._s3_file_map = {}

    def _load_state_from_file(self):
        try:
            with open(self.state_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.warning(f"State file not found at {self.state_path}. Starting with empty state.")
            return {}
        except json.JSONDecodeError:
            logging.error(f"Could not decode JSON from state file: {self.state_path}. Starting with empty state.")
            return {}

    @property
    def checker_name(self):
        return "S3ObjectChecker"

    def check(self) -> dict:

        s3_client = boto3.client('s3')
        source_bucket = self.source_location.get('bucket')
        source_prefix = self.source_location.get('prefix', '')
        temp_dir = self.middle_location.get('path', '/tmp/datanet_s3_downloads')

        if not source_bucket:
            raise ValueError("Source S3 bucket must be specified in the config under [parser.init.source]")

        os.makedirs(temp_dir, exist_ok=True)
        
        state_data = self._load_state_from_file()
        processed_objects = state_data.get('processed', {})
        
        new_local_files = []
        self._s3_file_map.clear() 

        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=source_bucket, Prefix=source_prefix)

            for page in pages:
                if "Contents" not in page:
                    continue
                for obj in page['Contents']:
                    object_key = obj['Key']
                    object_etag = obj['ETag'] 

                    if object_key.endswith('/'):
                        continue

                    if processed_objects.get(object_key) == object_etag:
                        continue

                    local_file_path = os.path.join(temp_dir, os.path.basename(object_key))
                    logging.info(f"New S3 object found: {object_key}. Downloading to {local_file_path}")
                    s3_client.download_file(source_bucket, object_key, local_file_path)

                    self._s3_file_map[local_file_path] = {"key": object_key, "etag": object_etag}
                    new_local_files.append(local_file_path)

        except Exception as e:
            logging.error(f"Failed to check for new files in S3 bucket {source_bucket}: {e}")

        return {'to do': new_local_files, 'failure': []}

    def save(self, completed: dict):

        success_files = completed.get('success', [])
        logging.info(f"Saving state for {len(success_files)} successfully processed files.")
        
        state_data = self._load_state_from_file()
        if 'processed' not in state_data:
            state_data['processed'] = {}
            
        for local_path in success_files:
            if local_path in self._s3_file_map:
                s3_details = self._s3_file_map[local_path]
                s3_key = s3_details['key']
                s3_etag = s3_details['etag']
                state_data['processed'][s3_key] = s3_etag
        
        state_dir = os.path.dirname(self.state_path)
        if not os.path.exists(state_dir):
            os.makedirs(state_dir)
        with open(self.state_path, 'w') as f:
            json.dump(state_data, f, indent=4)

    def clean(self):
        pass