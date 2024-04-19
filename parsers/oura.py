from source.common import ParserCommon
from source.checkers.api import OuraAPIDocumentChecker
from source.uploaders.simple import CopyUploaderMixin


class OuraRingDocumentParser(OuraAPIDocumentChecker, CopyUploaderMixin, ParserCommon):
    """"""
