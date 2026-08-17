from __future__ import annotations

import csv as csv_module
import io

from app.parsers.base import (
    BlockType,
    DocumentParser,
    ParsedBlock,
    ParsedDocument,
    decode_text,
    render_table_markdown,
)

# Rows are grouped so each block stays retrievable; every block repeats the
# header so a chunk is meaningful on its own.
ROWS_PER_BLOCK = 20


class CsvParser(DocumentParser):
    source_types = ("csv",)

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        text = decode_text(data)
        sample = text[:4096]
        try:
            dialect = csv_module.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv_module.Error:
            dialect = csv_module.excel
        reader = csv_module.reader(io.StringIO(text), dialect)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not rows:
            return ParsedDocument(title=filename, source_type="csv", blocks=[])

        headers, body = rows[0], rows[1:]
        blocks: list[ParsedBlock] = []
        for start in range(0, max(len(body), 1), ROWS_PER_BLOCK):
            group = body[start : start + ROWS_PER_BLOCK]
            blocks.append(
                ParsedBlock(
                    type=BlockType.TABLE,
                    text=render_table_markdown(headers, group, title=filename),
                    meta={
                        "table": {"headers": headers, "rows": group},
                        "row_start": start + 1,
                        "row_end": start + len(group),
                    },
                )
            )
        return ParsedDocument(
            title=filename,
            source_type="csv",
            blocks=blocks,
            meta={"row_count": len(body), "columns": headers},
        )
