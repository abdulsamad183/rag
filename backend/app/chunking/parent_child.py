from __future__ import annotations

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig
from app.chunking.recursive import recursive_split
from app.parsers.base import BlockType, ParsedDocument


class ParentChildChunker(Chunker):
    """Hierarchical / parent-child chunking.

    Document structure becomes a two-level hierarchy:
      section parents (large, contextual)  →  child chunks (small, precise)

    Children are embedded and retrieved; parents supply generation context
    (retrieval swaps a matched child for its parent — see EvidenceBuilder).
    """

    name = "parent_child"

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []

        # Group blocks into sections using the parser's heading structure;
        # fall back to page/size grouping for unstructured documents.
        sections: list[list] = []
        current: list = []
        current_len = 0
        current_path: str | None = None
        for block in document.blocks:
            if block.type == BlockType.HEADING:
                continue
            text = block.text.strip()
            if not text:
                continue
            boundary = (
                (current_path is not None and block.section_path != current_path)
                or current_len + len(text) > config.parent_chunk_size
            )
            if boundary and current:
                sections.append(current)
                current, current_len = [], 0
            current.append(block)
            current_len += len(text)
            current_path = block.section_path
        if current:
            sections.append(current)

        for section_blocks in sections:
            first = section_blocks[0]
            pages = [b.page for b in section_blocks if b.page]
            parent_text = "\n\n".join(b.text for b in section_blocks)
            parent = ChunkDraft(
                content=parent_text[: config.parent_chunk_size * 2],
                level="section",
                heading=first.heading,
                section_path=first.section_path,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
            )
            drafts.append(parent)
            parent_index = len(drafts) - 1

            for piece in recursive_split(parent_text, config.chunk_size):
                drafts.append(
                    ChunkDraft(
                        content=piece,
                        level="chunk",
                        heading=first.heading,
                        section_path=first.section_path,
                        page_start=min(pages) if pages else None,
                        page_end=max(pages) if pages else None,
                        parent_index=parent_index,
                    )
                )
        return drafts
