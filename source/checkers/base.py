import json
from abc import ABC, abstractmethod


def load_success_log(log_location):
    with open(log_location) as f:
        log = json.load(f)
    uploaded = log['success']
    return uploaded


class BaseChecker(ABC):
    """Base class for all checkers that defines the interface"""
    log_filename = 'upload_log.json'

    @property
    @abstractmethod
    def checker_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseChecker"

    @abstractmethod
    def check(self):
        """"""
        return {}  # Return a dict describing the data that needs to be uploaded

    @abstractmethod
    def save(self, completed):
        """"""

    def describe_parser(self):
        return {
            "git commit": "commitHash",  # TODO: implement commit hashing
            "base": str(type(self)),
            "checker": self.checker_name,
            "transformer": self.transformer_name,  # Defined in the TransformerMixin
            "uploader": self.uploader_name  # Defined in the UploaderMixin
        }
