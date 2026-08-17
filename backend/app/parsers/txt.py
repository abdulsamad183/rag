from __future__ import annotations

from app.parsers.base import BlockType, DocumentParser, ParsedBlock, ParsedDocument, decode_text
from app.utils.text import clean_text, split_paragraphs


class TxtParser(DocumentParser):
    source_types = ("txt",)

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        text = clean_text(decode_text(data))
        blocks = [ParsedBlock(type=BlockType.TEXT, text=p) for p in split_paragraphs(text)]
        return ParsedDocument(title=filename, source_type="txt", blocks=blocks)
