from __future__ import annotations

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig, split_with_overlap
from app.parsers.base import ParsedDocument


class ParagraphChunker(Chunker):
    """One chunk per parsed block (paragraph/table), merging tiny neighbors
    within the same section and splitting oversized paragraphs."""

    name = "paragraph"
    MIN_SIZE = 120

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        pending: ChunkDraft | None = None

        for block in document.blocks:
            text = block.text.strip()
            if not text:
                continue
            if pending is not None and (
                pending.section_path != block.section_path
                or len(pending.content) + len(text) + 1 > config.chunk_size
            ):
                drafts.append(pending)
                pending = None

            if len(text) > config.chunk_size:
                if pending is not None:
                    drafts.append(pending)
                    pending = None
                for piece in split_with_overlap(text, config.chunk_size, config.chunk_overlap):
                    drafts.append(
                        ChunkDraft(
                            content=piece, heading=block.heading, section_path=block.section_path,
                            page_start=block.page, page_end=block.page, meta=dict(block.meta),
                        )
                    )
                continue

            if pending is None:
                pending = ChunkDraft(
                    content=text, heading=block.heading, section_path=block.section_path,
                    page_start=block.page, page_end=block.page, meta=dict(block.meta),
                )
            else:
                pending.content += "\n\n" + text
                pending.page_end = block.page or pending.page_end

            if len(pending.content) >= self.MIN_SIZE:
                drafts.append(pending)
                pending = None

        if pending is not None:
            drafts.append(pending)
        return drafts
