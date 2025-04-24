import re
from pathlib import Path
from datetime import datetime, timezone

import boto3
from source.checkers.base import BaseChecker


class S3BucketChecker(BaseChecker):
    """Simple checker that looks for new files in an S3 bucket"""

    filter_defaults = {
        'min_size': 0,              # optional, minimum size in bytes
        'max_size': float('inf'),   # optional, maximum size in bytes
        'min_age': 0,               # optional, minimum time since last modified, in seconds
        'max_age': float('inf'),    # optional, maximum time since last modified, in seconds
        # 'regex_exclude': '',      # optional, objects with a key matching this regex will be skipped
        # 'regex_filter': '.',      # optional, only objects with a key matching this regex will be included
    }

    # Template source information
    source_location = {
        'path': 'unknown',          # required, local path to use as a staging ground for downloading dataa
        'bucket': 'unknown',        # required, name of the bucket to query for data
        'profile': 'default',       # optional, select the profile AWS CLI profile to use when connecting
        'aws_filters': [],          # optional, list of filter dicts to use when searching bucket for new data
        'local_filters': filter_defaults # optional, dict of filters to apply after the list of contents is downloaded
    }



    # Default behavior settings
    exclude_directories = True  # Exclude objects with zero size
    full_match_regex = False    # Allow partial matches when applying regex filters

    checker_name = 'S3BucketChecker'

    def get_bucket(self):
        """Establish a connection to the desired S3 bucket via boto3"""
        # If specified, explicitly one of the AWS CLI profiles to create connection
        if 'profile' in self.source_location:
            session = boto3.session.Session(profile_name=self.source_location['profile'])
            s3 = session.resource('s3')
        else:
            s3 = boto3.resource('s3')     # Use the AWS CLI default profile otherwise

        bucket = s3.Bucket(self.source_location['bucket'])
        return bucket

    def match_key(self, obj, pattern):
        """Match the S3 Object key against the regular expression"""
        if self.full_match_regex:
            match = re.match(pattern, obj)
        else:
            match = re.search(pattern, obj)
        return match is not None

    def list_bucket(self, bucket):
        """
        Return an iterable of all the contents of a bucket optionally matching any specified filters
        Note: these are only

        :param bucket: an S3 Bucket object
        """

        # TODO: do we still need to explicitly handle pagination?
        if 'aws_filters' in self.source_location:
            all_objects = bucket.objects.filter(Filters=self.source_location['aws_filters'])
        else:
            all_objects = bucket.objects.all()

        # Optionally exclude all directories (which have 0 size) right away
        if self.exclude_directories:
            all_objects = [obj for obj in all_objects if obj.size > 0]

        # Optionally apply any local filters
        if 'filters' in self.source_location:
            desired = self.source_location['filters']

            filters = self.filter_defaults
            filters.update(desired)

            # Apply the size filter is specified, with missing values filled in by defaults
            if 'min_size' in desired or 'max_size' in desired:
                all_objects = filter(
                    lambda o: filters['min_size'] <= o.size <= filters['max_size'],
                    all_objects
                )

            # Apply the file age filter is specified, with missing values filled in by defaults
            if 'min_age' in desired or 'max_age' in desired:
                now = datetime.now(tz=timezone.utc)
                def in_age_range(obj):
                    age = (now - obj.last_modified).total_seconds()
                    return filters['min_age'] <= age <= filters['max_age']
                all_objects = filter(in_age_range, all_objects)

            # Include only objects whos keys match the regex_filter
            if 'regex_filter' in desired:
                pattern = re.compile(desired['regex_filter'])
                def re_filter(obj):
                    return self.match_key(obj, pattern)
                all_objects = filter(re_filter, all_objects)

            # Exclude an objects that match the regex_exclude filter
            if 'regex_exclude' in desired:
                pattern = re.compile(desired['regex_exclude'])
                def exclude_filter(obj):
                    return self.match_key(obj, pattern)
                all_objects = filter(exclude_filter, all_objects)

        return all_objects

    def filter_new(self, objects):
        """
        Compare the list of objects in the S3 bucket to the state to determine which ones need to be processed

        :param objects:
        :return:
        """
        successes = self.load_successes()

        done_keys = {s['key']: s['timestamp'] for s in successes}
        todo = []

        for obj in objects:
            if obj.key in done_keys:
                continue    # TODO: consider adding in a check of changes since last update
            else:
                todo.append(obj)
        return todo

    def download_objects(self, todo):
        tasks, errors = [], []
        stage = self.source_location['path']
        for s3_obj in todo:
            try:
                out_path = Path(stage, s3_obj.key)
                s3_obj.download_file(out_path)
            except Exception as e:
                error_dict = {'obj': str(s3_obj), 'error': str(e), 'timestamp': datetime.now(timezone.utc).isoformat()}
                errors.append(error_dict)
            else:
                tasks.append(out_path)

        return tasks, errors

    def check(self):
        bucket = self.get_bucket()
        found = self.list_bucket(bucket)
        todo = self.filter_new(found)
        tasks, errors = self.download_objects(todo)
        return {'to do': tasks, 'failure': errors}


    def save(self, completed):
        """Log the files the that have been uploaded, along with all errors"""
        # TODO: make this work with the method of passing around dicts
        logged_data = self.load_state()
        logged_data['success'].extend(completed['success'])
        logged_data['failure'].extend(completed['failure'])
        self.write_state(logged_data)

    def clean(self):

        old_state = self.load_state()

        new_success = self.clean_old_success(old_state['success'])
        reduced_failures = self.clean_duplicate_failures(old_state['failure'])
        post_fix_failures = self.clean_fixed_failures(new_success, reduced_failures)

        self.write_state({'success': new_success, 'failure': post_fix_failures})