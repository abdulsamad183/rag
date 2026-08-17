"""Chunking framework.

A chunker turns a ``ParsedDocument`` into an ordered list of ``ChunkDraft``s.
Drafts may form a hierarchy: a draft with ``level="section"`` acts as a parent;
children reference it via ``parent_index`` (list index), which ingestion
resolves into ``parent_chunk_id`` foreign keys.

Sizes are measured in characters (~4 chars/token).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.parsers.base import ParsedDocument


@dataclass
class ChunkingConfig:
    strategy: str = "recursive"
    chunk_size: int = 800
    chunk_overlap: int = 120
    parent_chunk_size: int = 2400
    semantic_threshold: float = 0.62  # cosine-similarity boundary for semantic chunking

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ChunkingConfig:
        raw = raw or {}
        return cls(
            strategy=raw.get("strategy", "recursive"),
            chunk_size=int(raw.get("chunk_size", 800)),
            chunk_overlap=int(raw.get("chunk_overlap", 120)),
            parent_chunk_size=int(raw.get("parent_chunk_size", 2400)),
            semantic_threshold=float(raw.get("semantic_threshold", 0.62)),
        )


@dataclass
class ChunkDraft:
    content: str
    level: str = "chunk"  # "section" (parent) | "chunk" (leaf)
    heading: str = ""
    section_path: str = ""
    page_start: int | None = None
    page_end: int | None = None
    parent_index: int | None = None  # index of parent draft within the returned list
    meta: dict[str, Any] = field(default_factory=dict)


class Chunker(ABC):
    name: str = ""

    @abstractmethod
    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]: ...


def split_with_overlap(text: str, size: int, overlap: int) -> list[str]:
    """Split on word boundaries with character overlap."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    step = max(size - overlap, 1)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + int(size * 0.6), end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + step)
    return pieces


def pack_units(units: list[str], size: int, overlap_units: int = 1) -> list[str]:
    """Greedily pack small units (sentences/paragraphs) into chunks ≤ size,
    keeping ``overlap_units`` trailing units as overlap between chunks."""
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for unit in units:
        unit_len = len(unit) + 1
        if length + unit_len > size and current:
            chunks.append("\n".join(current).strip())
            tail = current[-overlap_units:] if overlap_units else []
            current = list(tail)
            length = sum(len(u) + 1 for u in current)
        current.append(unit)
        length += unit_len
    if current:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]
