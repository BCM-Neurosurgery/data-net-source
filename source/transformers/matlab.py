from source.transformers.base import BaseTransformer


class OpenMindTransformerMixin(BaseTransformer):

    transformer_name = "OpenMindTransformer"

    def transform(self, tasks):
        """
        Convert the raw JSON files from the Medtronic summit RC+S API to anonymized CSV files using OpenMind code
        https://github.com/openmind-consortium/Analysis-rcs-data
        """
        # TODO: move all of Raph's code here
