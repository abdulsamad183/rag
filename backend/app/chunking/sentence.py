from __future__ import annotations

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig, pack_units
from app.parsers.base import ParsedDocument
from app.utils.text import split_sentences


class SentenceChunker(Chunker):
    """Sentence-boundary chunking: never cuts a sentence in half."""

    name = "sentence"

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for block in document.blocks:
            if not block.text.strip():
                continue
            sentences = split_sentences(block.text) or [block.text]
            for piece in pack_units(sentences, config.chunk_size, overlap_units=1):
                drafts.append(
                    ChunkDraft(
                        content=piece,
                        heading=block.heading,
                        section_path=block.section_path,
                        page_start=block.page,
                        page_end=block.page,
                        meta=dict(block.meta),
                    )
                )
        return drafts
