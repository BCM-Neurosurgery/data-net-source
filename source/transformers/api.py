import json
import os.path

from source.transformers.base import BaseTransformer


class RuneFetchTransformerMixin(BaseTransformer):

    transformer_name = "RuneFetchTransformer"

    def transform(self, tasks):
        """
        Fetch the data from the RUNE API and save it to csvs
        :param tasks:
        :return:
        """



