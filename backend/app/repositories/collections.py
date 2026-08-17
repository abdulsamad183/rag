from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import Chunk, Collection, Document


async def list_collections(session: AsyncSession, user_id: uuid.UUID) -> list[Collection]:
    stmt = select(Collection).where(Collection.user_id == user_id).order_by(Collection.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def get_collection(session: AsyncSession, collection_id: uuid.UUID) -> Collection:
    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError(f"Collection {collection_id} not found")
    return collection


async def get_collections(session: AsyncSession, ids: list[uuid.UUID]) -> list[Collection]:
    if not ids:
        return []
    stmt = select(Collection).where(Collection.id.in_(ids))
    collections = list((await session.execute(stmt)).scalars().all())
    missing = set(ids) - {c.id for c in collections}
    if missing:
        raise NotFoundError(f"Collections not found: {', '.join(str(m) for m in missing)}")
    return collections


async def ensure_unique_name(session: AsyncSession, user_id: uuid.UUID, name: str) -> None:
    stmt = select(Collection.id).where(Collection.user_id == user_id, Collection.name == name)
    if (await session.execute(stmt)).first() is not None:
        raise ConflictError(f"A collection named '{name}' already exists")


async def bump_version(session: AsyncSession, collection_id: uuid.UUID) -> None:
    collection = await get_collection(session, collection_id)
    collection.version += 1


async def collection_stats(
    session: AsyncSession, collection_ids: list[uuid.UUID]
) -> dict[str, dict[str, int]]:
    if not collection_ids:
        return {}
    doc_stmt = (
        select(Document.collection_id, func.count(Document.id))
        .where(Document.collection_id.in_(collection_ids))
        .group_by(Document.collection_id)
    )
    chunk_stmt = (
        select(Chunk.collection_id, func.count(Chunk.id))
        .where(Chunk.collection_id.in_(collection_ids))
        .group_by(Chunk.collection_id)
    )
    docs = dict((await session.execute(doc_stmt)).all())
    chunks = dict((await session.execute(chunk_stmt)).all())
    return {
        str(cid): {"documents": int(docs.get(cid, 0)), "chunks": int(chunks.get(cid, 0))}
        for cid in collection_ids
    }
