"""Hierarchical document summarization (map-reduce over chunks).

Summaries are cached on the document row; regeneration is explicit."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.base import ChatMessage, GenerationParams
from app.llm.registry import get_llm
from app.models import Chunk, ChunkLevel
from app.rag import prompts
from app.repositories import documents as document_repo

logger = get_logger("summarize")

MAX_CHUNKS = 60
GROUP_SIZE = 8


async def summarize_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    provider: str | None = None,
    model: str | None = None,
    force: bool = False,
) -> str:
    document = await document_repo.get_document(session, document_id)
    cached = (document.meta or {}).get("summary", "")
    if cached and not force:
        return cached

    llm = get_llm(provider, model)
    stmt = (
        select(Chunk)
        .where(Chunk.document_id == document_id, Chunk.level == ChunkLevel.CHUNK)
        .order_by(Chunk.chunk_index)
        .limit(MAX_CHUNKS)
    )
    chunks = list((await session.execute(stmt)).scalars().all())
    if not chunks:
        return ""

    # Map: summarize groups of chunks; Reduce: summarize the summaries.
    partials: list[str] = []
    for start in range(0, len(chunks), GROUP_SIZE):
        group = chunks[start : start + GROUP_SIZE]
        text = "\n\n".join(c.content for c in group)[:12000]
        result = await llm.generate(
            [
                ChatMessage(role="system", content=prompts.SUMMARIZER_SYSTEM),
                ChatMessage(
                    role="user",
                    content=prompts.SUMMARIZER_USER.format(
                        kind="document section", max_words=120, text=text
                    ),
                ),
            ],
            GenerationParams(temperature=0.1, max_tokens=300),
        )
        partials.append(result.text.strip())

    if len(partials) == 1:
        summary = partials[0]
    else:
        combined = "\n\n".join(partials)[:12000]
        result = await llm.generate(
            [
                ChatMessage(role="system", content=prompts.SUMMARIZER_SYSTEM),
                ChatMessage(
                    role="user",
                    content=prompts.SUMMARIZER_USER.format(
                        kind="document (from section summaries)", max_words=250, text=combined
                    ),
                ),
            ],
            GenerationParams(temperature=0.1, max_tokens=500),
        )
        summary = result.text.strip()

    document.meta = {**(document.meta or {}), "summary": summary}
    await session.commit()
    return summary
