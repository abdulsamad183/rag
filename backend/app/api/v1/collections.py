from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.rate_limit import rate_limiter
from app.embeddings.registry import default_embedding_model
from app.models import Collection
from app.repositories import collections as collection_repo
from app.repositories import graph as graph_repo
from app.schemas.collections import CollectionCreate, CollectionOut, CollectionUpdate
from app.schemas.common import OkResponse

router = APIRouter(prefix="/collections", tags=["collections"])


def _to_out(collection: Collection, stats: dict[str, dict[str, int]]) -> CollectionOut:
    out = CollectionOut.model_validate(collection)
    entry = stats.get(str(collection.id), {})
    out.document_count = entry.get("documents", 0)
    out.chunk_count = entry.get("chunks", 0)
    return out


@router.get("", response_model=list[CollectionOut])
async def list_collections(session: DbSession, user: CurrentUser) -> list[CollectionOut]:
    collections = await collection_repo.list_collections(session, user.id)
    stats = await collection_repo.collection_stats(session, [c.id for c in collections])
    return [_to_out(c, stats) for c in collections]


@router.post("", response_model=CollectionOut, status_code=201,
             dependencies=[Depends(rate_limiter("default"))])
async def create_collection(
    payload: CollectionCreate, session: DbSession, user: CurrentUser
) -> CollectionOut:
    settings = get_settings()
    await collection_repo.ensure_unique_name(session, user.id, payload.name)
    provider = payload.embedding_provider or settings.default_embedding_provider
    if settings.local_mode:
        provider = "ollama"
    model = payload.embedding_model or default_embedding_model(provider)
    collection = Collection(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        embedding_provider=provider,
        embedding_model=model,
        chunking_config={
            "strategy": payload.validated_strategy(),
            "chunk_size": payload.chunk_size,
            "chunk_overlap": payload.chunk_overlap,
        },
        retrieval_config=payload.retrieval_config,
        graph_enabled=payload.graph_enabled,
        temporal_enabled=payload.temporal_enabled,
    )
    session.add(collection)
    await session.commit()
    return _to_out(collection, {})


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(collection_id: uuid.UUID, session: DbSession) -> CollectionOut:
    collection = await collection_repo.get_collection(session, collection_id)
    stats = await collection_repo.collection_stats(session, [collection.id])
    return _to_out(collection, stats)


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID, payload: CollectionUpdate, session: DbSession, user: CurrentUser
) -> CollectionOut:
    collection = await collection_repo.get_collection(session, collection_id)
    if payload.name and payload.name != collection.name:
        await collection_repo.ensure_unique_name(session, user.id, payload.name)
        collection.name = payload.name
    if payload.description is not None:
        collection.description = payload.description
    if payload.graph_enabled is not None:
        collection.graph_enabled = payload.graph_enabled
    if payload.temporal_enabled is not None:
        collection.temporal_enabled = payload.temporal_enabled
    if payload.retrieval_config is not None:
        collection.retrieval_config = payload.retrieval_config
    if payload.chunking_config is not None:
        collection.chunking_config = {**collection.chunking_config, **payload.chunking_config}
    await session.commit()
    stats = await collection_repo.collection_stats(session, [collection.id])
    return _to_out(collection, stats)


@router.delete("/{collection_id}", response_model=OkResponse)
async def delete_collection(collection_id: uuid.UUID, session: DbSession) -> OkResponse:
    collection = await collection_repo.get_collection(session, collection_id)
    await graph_repo.delete_collection_graph(session, collection_id)
    await session.delete(collection)  # documents/chunks cascade
    await session.commit()
    return OkResponse()
