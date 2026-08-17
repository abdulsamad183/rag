"""Chunk search SQL: vector similarity (pgvector), keyword full-text
(websearch_to_tsquery + ts_rank_cd), metadata filtering, hierarchy lookups."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, ChunkLevel, Document
from app.retrieval.base import QueryFilters, RetrievedChunk


def _row_to_chunk(chunk: Chunk, document: Document, source: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        content=chunk.content,
        score=score,
        scores={source: score},
        document_name=document.title or document.filename,
        source_type=document.source_type,
        heading=chunk.heading,
        section_path=chunk.section_path,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        level=chunk.level,
        parent_id=chunk.parent_id,
        trust=document.trust,
        meta={
            **(chunk.meta or {}),
            "content_hash": chunk.content_hash,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "valid_from": document.valid_from.isoformat() if document.valid_from else None,
            "valid_to": document.valid_to.isoformat() if document.valid_to else None,
            "url": (document.meta or {}).get("url", ""),
        },
    )


def _apply_filters(stmt: Select, filters: QueryFilters | None) -> Select:
    if filters is None or filters.is_empty():
        return stmt
    if filters.document_ids:
        stmt = stmt.where(Chunk.document_id.in_(filters.document_ids))
    if filters.source_types:
        stmt = stmt.where(Document.source_type.in_(filters.source_types))
    if filters.author:
        stmt = stmt.where(Document.meta["author"].astext.ilike(f"%{filters.author}%"))
    if filters.tags:
        stmt = stmt.where(Document.meta["tags"].contains(filters.tags))
    if filters.section:
        stmt = stmt.where(
            or_(
                Chunk.section_path.ilike(f"%{filters.section}%"),
                Chunk.heading.ilike(f"%{filters.section}%"),
            )
        )
    if filters.valid_at is not None:
        # Temporal validity: document must be valid at the requested time.
        # Documents without validity metadata are not excluded (unknown ≠ invalid).
        stmt = stmt.where(
            or_(Document.valid_from.is_(None), Document.valid_from <= filters.valid_at)
        ).where(or_(Document.valid_to.is_(None), Document.valid_to >= filters.valid_at))
    return stmt


def _base_query(collection_ids: list[uuid.UUID], filters: QueryFilters | None) -> Select:
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.collection_id.in_(collection_ids))
        .where(Chunk.level == ChunkLevel.CHUNK)
        .where(Document.status == "completed")
    )
    return _apply_filters(stmt, filters)


async def search_vector(
    session: AsyncSession,
    collection_ids: list[uuid.UUID],
    embedding: list[float],
    limit: int,
    filters: QueryFilters | None = None,
) -> list[RetrievedChunk]:
    distance = Chunk.embedding.cosine_distance(embedding)
    stmt = (
        _base_query(collection_ids, filters)
        .add_columns(distance.label("distance"))
        .where(Chunk.embedding.is_not(None))
        .order_by(distance.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    results = []
    for chunk, document, dist in rows:
        similarity = max(0.0, 1.0 - float(dist))  # cosine distance -> similarity
        results.append(_row_to_chunk(chunk, document, "vector", similarity))
    return results


async def search_keyword(
    session: AsyncSession,
    collection_ids: list[uuid.UUID],
    query_text: str,
    limit: int,
    filters: QueryFilters | None = None,
) -> list[RetrievedChunk]:
    tsquery = func.websearch_to_tsquery("english", query_text)
    rank = func.ts_rank_cd(Chunk.tsv, tsquery)
    stmt = (
        _base_query(collection_ids, filters)
        .add_columns(rank.label("rank"))
        .where(Chunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_chunk(chunk, doc, "keyword", float(r)) for chunk, doc, r in rows]


async def get_chunks_by_ids(
    session: AsyncSession, chunk_ids: list[uuid.UUID]
) -> list[RetrievedChunk]:
    if not chunk_ids:
        return []
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(chunk_ids))
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_chunk(chunk, doc, "lookup", 1.0) for chunk, doc in rows]


async def get_parent_chunks(
    session: AsyncSession, parent_ids: list[uuid.UUID]
) -> dict[str, RetrievedChunk]:
    """Fetch parent (section-level) chunks for parent-child context expansion."""
    if not parent_ids:
        return {}
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(parent_ids))
    )
    rows = (await session.execute(stmt)).all()
    return {str(chunk.id): _row_to_chunk(chunk, doc, "parent", 1.0) for chunk, doc in rows}


async def get_chunk_with_document(
    session: AsyncSession, chunk_id: uuid.UUID
) -> tuple[Chunk, Document] | None:
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id == chunk_id)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def count_chunks(session: AsyncSession, collection_ids: list[uuid.UUID]) -> int:
    stmt = select(func.count(Chunk.id)).where(Chunk.collection_id.in_(collection_ids))
    return int((await session.execute(stmt)).scalar() or 0)


async def sibling_chunks_by_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    limit: int = 5,
) -> list[RetrievedChunk]:
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.document_id == document_id)
        .where(Chunk.level == ChunkLevel.CHUNK)
        .order_by(Chunk.chunk_index)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_chunk(chunk, doc, "document", 0.5) for chunk, doc in rows]


async def fetch_document_meta(
    session: AsyncSession, document_ids: list[uuid.UUID]
) -> dict[str, dict[str, Any]]:
    if not document_ids:
        return {}
    stmt = select(Document).where(Document.id.in_(document_ids))
    docs = (await session.execute(stmt)).scalars().all()
    return {
        str(d.id): {
            "title": d.title or d.filename,
            "source_type": d.source_type,
            "published_at": d.published_at.isoformat() if d.published_at else None,
            "trust": d.trust,
            "meta": d.meta,
        }
        for d in docs
    }
