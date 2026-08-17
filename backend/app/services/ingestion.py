"""Document ingestion pipeline.

    parse → clean → structure → chunk (dedupe) → embed (batched, cached) →
    index (FTS is automatic; vector index ensured) → completed

Runs inside a worker (or inline in dev). Progress and stage are persisted on
the document row after every stage so the UI can poll honestly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import ChunkDraft, ChunkingConfig, get_chunker
from app.core.errors import IngestionError
from app.core.logging import get_logger
from app.embeddings.registry import get_embedder
from app.models import Chunk, ChunkLevel, Collection, Document, DocumentStatus
from app.parsers import get_parser
from app.repositories import collections as collection_repo
from app.repositories import documents as document_repo
from app.services.indexing import ensure_vector_index
from app.storage import get_storage
from app.utils.hashing import sha256_text
from app.utils.text import clean_text, estimate_tokens, extract_years

logger = get_logger("ingestion")

_STAGE_PROGRESS = {
    DocumentStatus.PARSING: 0.15,
    DocumentStatus.CHUNKING: 0.35,
    DocumentStatus.EMBEDDING: 0.55,
    DocumentStatus.INDEXING: 0.9,
    DocumentStatus.COMPLETED: 1.0,
}


async def _set_stage(session: AsyncSession, document: Document, status: str) -> None:
    document.status = status
    document.progress = _STAGE_PROGRESS.get(status, document.progress)
    await session.commit()


async def ingest_document(session: AsyncSession, document_id: uuid.UUID) -> None:
    document = await document_repo.get_document(session, document_id)
    collection = await collection_repo.get_collection(session, document.collection_id)
    try:
        await _ingest(session, document, collection)
    except Exception as exc:
        await session.rollback()
        document = await document_repo.get_document(session, document_id)
        document.status = DocumentStatus.FAILED
        document.error = str(exc)[:2000]
        await session.commit()
        logger.error("ingestion_failed", document_id=str(document_id), error=str(exc)[:300])
        raise


async def _ingest(session: AsyncSession, document: Document, collection: Collection) -> None:
    storage = get_storage()

    # ---- parse ----
    await _set_stage(session, document, DocumentStatus.PARSING)
    raw = await storage.read(document.storage_path)
    parser = get_parser(document.source_type)
    parsed = parser.parse(raw, document.filename)
    if not document.title:
        document.title = parsed.title[:512]
    document.page_count = int(parsed.meta.get("page_count", 0))
    doc_meta = dict(document.meta or {})
    doc_meta.update({k: v for k, v in parsed.meta.items() if k not in ("page_count",)})
    document.meta = doc_meta
    _infer_temporal(document, parsed.meta)

    # ---- chunk ----
    await _set_stage(session, document, DocumentStatus.CHUNKING)
    config = ChunkingConfig.from_dict(collection.chunking_config)
    embedder = get_embedder(collection.embedding_provider, collection.embedding_model)

    async def embed_fn(texts: list[str]) -> list[list[float]]:
        vectors, _ = await embedder.embed(texts)
        return vectors

    chunker = get_chunker(config.strategy, embed_fn if config.strategy == "semantic" else None)
    drafts = await chunker.chunk(parsed, config)
    drafts = _dedupe_drafts(drafts)
    if not drafts:
        raise IngestionError("Document produced no indexable content")

    # Replace any previous version's chunks (idempotent reingestion).
    await document_repo.delete_document_chunks(session, document.id)

    chunk_rows: list[Chunk] = []
    for index, draft in enumerate(drafts):
        content = clean_text(draft.content)
        chunk_rows.append(
            Chunk(
                id=uuid.uuid4(),
                document_id=document.id,
                collection_id=collection.id,
                level=ChunkLevel.SECTION if draft.level == "section" else ChunkLevel.CHUNK,
                chunk_index=index,
                doc_version=document.current_version,
                heading=draft.heading[:512],
                section_path=draft.section_path[:1024],
                page_start=draft.page_start,
                page_end=draft.page_end,
                content=content,
                content_hash=sha256_text(content),
                token_count=estimate_tokens(content),
                meta={
                    **draft.meta,
                    "document_name": document.title or document.filename,
                    "source_type": document.source_type,
                    "chunk_strategy": config.strategy,
                },
            )
        )
    # Wire parent-child links (drafts reference parents by list index).
    for draft, row in zip(drafts, chunk_rows, strict=True):
        if draft.parent_index is not None:
            row.parent_id = chunk_rows[draft.parent_index].id

    # ---- embed (leaf chunks only) ----
    await _set_stage(session, document, DocumentStatus.EMBEDDING)
    leaves = [row for row in chunk_rows if row.level == ChunkLevel.CHUNK]
    vectors, stats = await embedder.embed([row.content for row in leaves])
    dimension = len(vectors[0]) if vectors else 0
    _check_embedding_compat(collection, embedder, dimension)
    for row, vector in zip(leaves, vectors, strict=True):
        row.embedding = vector
        row.embedding_model = f"{embedder.provider}/{embedder.model}"
    logger.info(
        "embedding_done",
        document_id=str(document.id),
        chunks=len(leaves),
        cache_hits=stats.cache_hits,
        tokens=stats.prompt_tokens,
        latency_ms=stats.latency_ms,
    )

    # ---- index ----
    await _set_stage(session, document, DocumentStatus.INDEXING)
    session.add_all(chunk_rows)
    if collection.embedding_dimension == 0 and dimension:
        collection.embedding_dimension = dimension
    document.chunk_count = len(chunk_rows)
    await ensure_vector_index(session, dimension)
    await collection_repo.bump_version(session, collection.id)

    document.status = DocumentStatus.COMPLETED
    document.progress = 1.0
    document.error = ""
    await session.commit()
    logger.info(
        "ingestion_completed",
        document_id=str(document.id),
        chunks=len(chunk_rows),
        strategy=config.strategy,
    )


def _dedupe_drafts(drafts: list[ChunkDraft]) -> list[ChunkDraft]:
    """Chunk-level exact dedup, preserving parent links by index remapping."""
    seen: dict[str, int] = {}
    kept: list[ChunkDraft] = []
    index_map: dict[int, int] = {}
    for old_index, draft in enumerate(drafts):
        key = sha256_text(draft.content.strip().lower())
        if key in seen and draft.level != "section":
            index_map[old_index] = seen[key]
            continue
        seen.setdefault(key, len(kept))
        index_map[old_index] = len(kept)
        kept.append(draft)
    for draft in kept:
        if draft.parent_index is not None:
            draft.parent_index = index_map.get(draft.parent_index, draft.parent_index)
    return kept


def _check_embedding_compat(collection: Collection, embedder, dimension: int) -> None:
    """Embeddings from different models must never share a vector space."""
    if collection.embedding_dimension and dimension and collection.embedding_dimension != dimension:
        raise IngestionError(
            f"Embedding dimension mismatch: collection expects "
            f"{collection.embedding_dimension}, model '{embedder.model}' produced {dimension}. "
            f"Reindex the collection to switch embedding models."
        )


def _infer_temporal(document: Document, meta: dict) -> None:
    """Best-effort published_at from metadata (deterministic; user-overridable)."""
    if document.published_at is not None:
        return
    for key in ("published_at", "date", "created"):
        value = meta.get(key)
        if isinstance(value, str) and len(value) >= 4:
            years = extract_years(value)
            if years:
                document.published_at = datetime(years[0], 1, 1, tzinfo=UTC)
                return
