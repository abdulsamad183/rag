from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig
from app.parsers.base import ParsedDocument
from app.utils.text import cosine, split_sentences

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


class SemanticChunker(Chunker):
    """Embedding-driven boundaries: consecutive sentence windows whose cosine
    similarity drops below the threshold start a new chunk. Requires an
    embedding function; ingestion injects the collection's embedder."""

    name = "semantic"

    def __init__(self, embed_fn: EmbedFn | None = None):
        self.embed_fn = embed_fn

    async def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[ChunkDraft]:
        if self.embed_fn is None:
            # No embedder available (e.g. offline unit tests) — degrade to
            # sentence packing rather than failing ingestion.
            from app.chunking.sentence import SentenceChunker

            return await SentenceChunker().chunk(document, config)

        drafts: list[ChunkDraft] = []
        for block in document.blocks:
            text = block.text.strip()
            if not text:
                continue
            sentences = split_sentences(text)
            if len(sentences) <= 2:
                if text:
                    drafts.append(self._draft(text, block))
                continue

            vectors = await self.embed_fn(sentences)
            groups: list[list[str]] = [[sentences[0]]]
            group_len = len(sentences[0])
            for i in range(1, len(sentences)):
                similarity = cosine(vectors[i - 1], vectors[i])
                new_boundary = similarity < config.semantic_threshold
                too_big = group_len + len(sentences[i]) > config.chunk_size
                if new_boundary or too_big:
                    groups.append([sentences[i]])
                    group_len = len(sentences[i])
                else:
                    groups[-1].append(sentences[i])
                    group_len += len(sentences[i])

            for group in groups:
                content = " ".join(group).strip()
                if content:
                    drafts.append(self._draft(content, block))
        return drafts

    @staticmethod
    def _draft(content: str, block) -> ChunkDraft:
        return ChunkDraft(
            content=content,
            heading=block.heading,
            section_path=block.section_path,
            page_start=block.page,
            page_end=block.page,
            meta=dict(block.meta),
        )
