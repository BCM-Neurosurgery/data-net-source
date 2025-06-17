# The checker code for S3 bucket access goes here.

import boto3
import os
from .base import BaseChecker  # Imports the abstract base class for checkers
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

        #Add a paginator to handle large buckets with try and except for error handling

    def save(self, completed: dict):
        pass


    def clean(self):
        pass
