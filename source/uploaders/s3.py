# The uploader code for S3 bucket goes here.

import boto3
import os
from .base import BaseUploader 
import logging

class S3UploaderMixin(BaseUploader):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_processed_files = []

    @property
    def uploader_name(self):
        return "S3Uploader"

    def upload(self, ready: dict) -> dict:

        files_to_process = ready.get('to upload', [])
        self._last_processed_files = files_to_process

        s3_client = boto3.client('s3')
        target_bucket = self.target_location.get('bucket')
        target_prefix = self.target_location.get('prefix', '')

        if not target_bucket:
            raise ValueError("Target S3 bucket must be specified in the config under [parser.init.target]")

        upload_metadata = {'success': [], 'failure': []}

        
    def clean(self):
        
        pass 