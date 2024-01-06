from source.base import ParserCommon
from source.checkers import WholeDirCheckerMixin
from source.transformers import OpenMindTransformerMixin
from source.uploaders import BucketUploaderMixin


class RCSParser(WholeDirCheckerMixin, OpenMindTransformerMixin, BucketUploaderMixin, ParserCommon):
    """"""
