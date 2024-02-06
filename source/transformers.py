from copy import copy
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


class OpenMindTransformerMixin(BaseTransformer):

    transformer_name = "OpenMindTransformer"

    def transform(self, tasks):
        """
        Convert the raw JSON files from the Medtronic summit RC+S API to anonymized CSV files using OpenMind code
        https://github.com/openmind-consortium/Analysis-rcs-data
        """
        # TODO: move all of Raph's code here


class RuneFetchTransformerMixin(BaseTransformer):

    transformer_name = "RuneFetchTransformer"

    def transform(self, tasks):
        """
        Fetch the data from the RUNE API and save it to csvs
        :param tasks:
        :return:
        """


class OpenPoseTransformerMixin(BaseTransformer):

    transformer_name = "OpenPoseTransformer"

    def transform(self, tasks):
        """
        Use OpenPose to process video into pose data
        :param tasks:
        :return:
        """
