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


class NullTransformerMixin(BaseTransformer):
    """The null transformation that does nothing"""

    transformer_name = "NullTransformer"

    def transform(self, tasks):
        """Null transformation that does nothing, so just pass back the original files as ready for upload"""
        return {'to upload': tasks['to do'], 'failure': tasks['failure']}


