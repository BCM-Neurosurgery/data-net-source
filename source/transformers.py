from copy import copy


class NullTransformer:
    """The null transformation that does nothing"""

    def transform(self, todo):
        """Null transformation that does nothing, so just pass back the original files as ready for upload"""
        return copy(todo)


class OpenMindTransformerMixin:

    def transform(self, todo):
        """
        Convert the raw JSON files from the Medtronic summit RC+S API to anonymized CSV files using OpenMind code
        https://github.com/openmind-consortium/Analysis-rcs-data
        """
        # TODO: move all of Raph's code here

