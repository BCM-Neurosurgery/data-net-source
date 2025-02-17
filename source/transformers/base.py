from abc import ABC, abstractmethod


class BaseTransformer(ABC):

    @property
    @abstractmethod
    def transformer_name(self):
        """Replace with a simple attribute naming the mixin class for later reference"""
        return "BaseTransformer"

    @abstractmethod
    def transform(self, tasks):
        """
        Convert data from the raw form to a format suitable for upload to the data lake
        This usually will involve reading data from the original source and saving a transformed version to the disk

        :param tasks: dict with a list of objects to transform and a list of known failures
            Should be of the form {'to do': [], 'failure': []}
        :returns: a dict describing the data to upload and failures
        """
        return {'to upload': [], 'failure': []}


