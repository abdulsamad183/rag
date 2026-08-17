"""Parser abstraction. Every format is normalized into ``ParsedDocument`` —
an ordered list of typed blocks that preserves structure (headings, pages,
sections, tables) instead of flattening everything into a single string.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class BlockType:
    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    CODE = "code"


@dataclass
class ParsedBlock:
    type: str
    text: str
    page: int | None = None
    heading: str = ""            # nearest heading above this block
    section_path: str = ""       # "Intro > Background"
    heading_level: int = 0
    meta: dict[str, Any] = field(default_factory=dict)  # table headers/rows, row idx, json path…


@dataclass
class ParsedDocument:
    title: str
    source_type: str
    blocks: list[ParsedBlock] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)  # page_count, url, author, language…

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())


class DocumentParser(ABC):
    source_types: tuple[str, ...] = ()

    def can_parse(self, source_type: str) -> bool:
        return source_type in self.source_types

    @abstractmethod
    def parse(self, data: bytes, filename: str) -> ParsedDocument: ...


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue
    return data.decode("utf-8", errors="replace")


def render_table_markdown(headers: list[str], rows: list[list[str]], title: str = "") -> str:
    """Readable text rendering of a table; structure is kept in block.meta."""
    lines: list[str] = []
    if title:
        lines.append(f"Table: {title}")
    if headers:
        lines.append(" | ".join(headers))
        lines.append(" | ".join("---" for _ in headers))
    for row in rows:
        lines.append(" | ".join(str(cell) for cell in row))
    return "\n".join(lines)
