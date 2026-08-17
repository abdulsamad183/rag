from __future__ import annotations

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig
from app.chunking.recursive import recursive_split
from app.parsers.base import BlockType, ParsedDocument


class MarkdownAwareChunker(Chunker):
    """Section-aware chunking driven by the heading hierarchy the parser
    preserved. Chunks never cross section boundaries and each chunk is
    prefixed with its section path for self-contained retrieval."""

    name = "markdown"

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        section_blocks: list = []
        section_key: tuple[str, str] | None = None

        def flush() -> None:
            nonlocal section_blocks
            if not section_blocks:
                return
            heading = section_blocks[0].heading
            path = section_blocks[0].section_path
            pages = [b.page for b in section_blocks if b.page]
            text = "\n\n".join(b.text for b in section_blocks if b.type != BlockType.HEADING)
            if text.strip():
                prefix = f"[{path}]\n" if path else ""
                for piece in recursive_split(text, config.chunk_size - len(prefix)):
                    drafts.append(
                        ChunkDraft(
                            content=prefix + piece,
                            heading=heading,
                            section_path=path,
                            page_start=min(pages) if pages else None,
                            page_end=max(pages) if pages else None,
                        )
                    )
            section_blocks = []

        for block in document.blocks:
            key = (block.section_path, block.heading)
            if section_key is not None and key != section_key and block.type == BlockType.HEADING:
                flush()
            section_key = key
            section_blocks.append(block)
        flush()
        return drafts
