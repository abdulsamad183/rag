"""Document upload, versioning, deduplication, and deletion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Collection, Document, DocumentStatus
from app.repositories import collections as collection_repo
from app.repositories import documents as document_repo
from app.security.files import validate_upload
from app.storage import get_storage
from app.utils.hashing import sha256_bytes

logger = get_logger("documents")


async def upload_document(
    session: AsyncSession,
    collection: Collection,
    filename: str,
    data: bytes,
    meta: dict | None = None,
) -> tuple[Document, bool]:
    """Store an upload and create/update the Document row.

    Returns (document, is_new_content). Duplicate content (same hash) in the
    same collection is rejected as a no-op; a changed file with the same name
    becomes a new version of the existing document.
    """
    safe_name, source_type = validate_upload(filename, data)
    content_hash = sha256_bytes(data)

    duplicate = await document_repo.find_by_hash(session, collection.id, content_hash)
    if duplicate is not None:
        logger.info("duplicate_upload_skipped", document_id=str(duplicate.id))
        return duplicate, False

    existing = await document_repo.find_by_filename(session, collection.id, safe_name)
    storage = get_storage()

    if existing is not None:
        existing.current_version += 1
        existing.content_hash = content_hash
        existing.size_bytes = len(data)
        existing.status = DocumentStatus.QUEUED
        existing.progress = 0.0
        existing.error = ""
        key = f"{collection.id}/{existing.id}/v{existing.current_version}/{safe_name}"
        existing.storage_path = await storage.save(key, data)
        await document_repo.add_version(
            session, existing, existing.storage_path, len(data), content_hash
        )
        if meta:
            existing.meta = {**(existing.meta or {}), **meta}
            _apply_temporal_meta(existing, meta)
        await session.commit()
        return existing, True

    document = Document(
        id=uuid.uuid4(),
        collection_id=collection.id,
        filename=safe_name,
        source_type=source_type,
        size_bytes=len(data),
        content_hash=content_hash,
        storage_path="",
        status=DocumentStatus.QUEUED,
        meta=meta or {},
    )
    if meta:
        _apply_temporal_meta(document, meta)
    key = f"{collection.id}/{document.id}/v1/{safe_name}"
    document.storage_path = await storage.save(key, data)
    session.add(document)
    await document_repo.add_version(session, document, document.storage_path, len(data), content_hash)
    await session.commit()
    return document, True


def _apply_temporal_meta(document: Document, meta: dict) -> None:
    for field in ("published_at", "valid_from", "valid_to"):
        value = meta.get(field)
        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                setattr(document, field, parsed)
            except ValueError:
                pass
    if "trust" in meta:
        try:
            document.trust = min(1.0, max(0.0, float(meta["trust"])))
        except (TypeError, ValueError):
            pass


async def delete_document(session: AsyncSession, document_id: uuid.UUID) -> None:
    document = await document_repo.get_document(session, document_id)
    storage = get_storage()
    try:
        await storage.delete(document.storage_path)
    except Exception:  # noqa: BLE001 — DB row removal must not be blocked by FS state
        logger.warning("storage_delete_failed", document_id=str(document_id))
    collection_id = document.collection_id
    await session.delete(document)  # chunks/citations cascade
    await collection_repo.bump_version(session, collection_id)
    await session.commit()
