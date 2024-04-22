from source.common import ParserCommon
from source.checkers.api import OuraAPIDocumentChecker
from source.uploaders.simple import CopyUploaderMixin
from source.transformers.api import OuraDocTransformer


class OuraRingDocumentParser(OuraAPIDocumentChecker, OuraDocTransformer, CopyUploaderMixin, ParserCommon):
    """"""
