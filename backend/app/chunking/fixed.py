from __future__ import annotations

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig, split_with_overlap
from app.parsers.base import ParsedDocument


class FixedSizeChunker(Chunker):
    name = "fixed"

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for block in document.blocks:
            if not block.text.strip():
                continue
            for piece in split_with_overlap(block.text, config.chunk_size, config.chunk_overlap):
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
