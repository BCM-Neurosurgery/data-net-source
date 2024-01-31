from source.base import ParserCommon
from source.checkers.local import FileCheckerMixin, StreamedFileCheckerMixin
from source.transformers import NullTransformerMixin
from source.uploaders import CopyUploaderMixin


class TestParser(FileCheckerMixin, NullTransformerMixin, CopyUploaderMixin, ParserCommon):
    """"""


parser = TestParser(
    r'D:\Work\DataNet\TestData\sources\blackrock',
    r'D:\Work\DataNet\TestData\parsers\test_parser',
    r'D:\Work\DataNet\TestData\lake\blackrock'
)
parser.process()
