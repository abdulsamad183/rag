from app.core.errors import UnsupportedFileTypeError
from app.parsers.base import BlockType, DocumentParser, ParsedBlock, ParsedDocument
from app.parsers.csv import CsvParser
from app.parsers.docx import DocxParser
from app.parsers.html import HtmlParser
from app.parsers.json import JsonParser
from app.parsers.markdown import MarkdownParser
from app.parsers.pdf import PdfParser
from app.parsers.txt import TxtParser

_PARSERS: list[DocumentParser] = [
    PdfParser(),
    TxtParser(),
    MarkdownParser(),
    DocxParser(),
    HtmlParser(),
    CsvParser(),
    JsonParser(),
]


def get_parser(source_type: str) -> DocumentParser:
    for parser in _PARSERS:
        if parser.can_parse(source_type):
            return parser
    raise UnsupportedFileTypeError(f"No parser registered for source type '{source_type}'")


__all__ = [
    "BlockType",
    "DocumentParser",
    "ParsedBlock",
    "ParsedDocument",
    "get_parser",
]
