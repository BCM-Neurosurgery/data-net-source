from source.transformers.base import BaseTransformer


class OpenPoseTransformerMixin(BaseTransformer):

    transformer_name = "OpenPoseTransformer"

    def transform(self, tasks):
        """
        Use OpenPose to process video into pose data
        :param tasks:
        :return:
        """
