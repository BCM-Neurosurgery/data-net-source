from source.common import ParserCommon
from source.checkers.api.oura import OuraAPIDocumentChecker, OuraAPIStreamChecker
from source.uploaders.simple import CopyUploaderMixin


class OuraRingDocumentParser(OuraAPIDocumentChecker, CopyUploaderMixin, ParserCommon):
    """
    This parser is responsible for pulling documents from the OuraRing and copying them to the data lake

    A 'document' is defined by OuraRing as a single unit of data with a unique identifier. The contents of this
    document are different for each modality (and not all modalities are stored as documents).

    To avoid duplicating work, the Checker for this parser will compare all recently uploaded documents with the list
    of saved documents, and copy all the data for days and modalities where new documents have been found. See the
    Checker definition for more information.

    The parser is intended to run on the same machine that stores the data, so the data transfer is a simple local copy
    """


class OuraRingStreamParser(OuraAPIStreamChecker, CopyUploaderMixin, ParserCommon):
    """
    """
