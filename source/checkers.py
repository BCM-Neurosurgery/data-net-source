import json
import os
from abc import ABC, abstractmethod


def load_success_log(log_location):
    with open(log_location) as f:
        log = json.load(f)
    uploaded = log['success']
    return uploaded


class BaseChecker(ABC):
    """Base class for all checkers that defines the interface"""

    @property
    @abstractmethod
    def checker_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseChecker"

    @abstractmethod
    def check(self, source_dir):
        """"""
        return {}  # Return a dict describing the data that needs to be uploaded


class DirectoryCheckerMixin(BaseChecker):
    """
    Mixin to a parser that checks whether an entire directory has already been uploaded or not
    """

    checker_name = "DirectoryCheckerMixin"

    def check(self, source_dir):
        dirs_here = [
            directory for directory in os.listdir(source_dir)
            if os.path.isdir(os.path.join(source_dir, directory))
        ]

        # TODO: the log will need to be parsed somehow, not sure what other info we will save here
        successes = load_success_log(os.path.join(source_dir, 'upload_log.json'))
        already_uploaded = [os.path.join(obj['checked'], obj['uploaded']) for obj in successes]

        to_upload = [
            directory for directory in dirs_here
            if directory not in already_uploaded
        ]
        return to_upload

    def save(self, completed):
        # TODO: Implement a save
        pass
