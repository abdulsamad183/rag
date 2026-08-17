from __future__ import annotations

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig
from app.parsers.base import ParsedDocument

SEPARATORS = ["\n\n", "\n", ". ", " "]


def recursive_split(text: str, size: int, separators: list[str] | None = None) -> list[str]:
    """Classic recursive character splitting: try the coarsest separator first,
    recurse into pieces that are still too large."""
    seps = separators if separators is not None else SEPARATORS
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    if not seps:
        return [text[i : i + size].strip() for i in range(0, len(text), size)]

    sep, rest = seps[0], seps[1:]
    parts = [p for p in text.split(sep) if p.strip()]
    if len(parts) == 1:
        return recursive_split(text, size, rest)

    result: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            result.append(current.strip())
        if len(part) > size:
            result.extend(recursive_split(part, size, rest))
            current = ""
        else:
            current = part
    if current:
        result.append(current.strip())
    return [r for r in result if r]


class RecursiveChunker(Chunker):
    name = "recursive"

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        # Merge contiguous blocks within a section, then split recursively —
        # gives natural boundaries while respecting document structure.
        group_text: list[str] = []
        group_meta: dict = {}

        def flush() -> None:
            if not group_text:
                return
            merged = "\n\n".join(group_text)
            overlap_tail = ""
            for piece in recursive_split(merged, config.chunk_size):
                content = (overlap_tail + piece).strip() if overlap_tail else piece
                drafts.append(
                    ChunkDraft(
                        content=content,
                        heading=group_meta.get("heading", ""),
                        section_path=group_meta.get("section_path", ""),
                        page_start=group_meta.get("page_start"),
                        page_end=group_meta.get("page_end"),
                    )
                )
                overlap_tail = piece[-config.chunk_overlap :] + "\n" if config.chunk_overlap else ""
            group_text.clear()
            group_meta.clear()

        for block in document.blocks:
            text = block.text.strip()
            if not text:
                continue
            if group_meta and group_meta.get("section_path") != block.section_path:
                flush()
            if not group_meta:
                group_meta.update(
                    heading=block.heading, section_path=block.section_path,
                    page_start=block.page, page_end=block.page,
                )
            group_meta["page_end"] = block.page or group_meta.get("page_end")
            group_text.append(text)
        flush()
        return drafts
