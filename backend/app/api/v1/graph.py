from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DbSession
from app.repositories import collections as collection_repo
from app.repositories import graph as graph_repo
from app.schemas.common import OkResponse
from app.schemas.graph import GraphEdge, GraphNode, GraphOut
from app.workers.queue import enqueue

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/collections/{collection_id}", response_model=GraphOut)
async def get_collection_graph(collection_id: uuid.UUID, session: DbSession) -> GraphOut:
    await collection_repo.get_collection(session, collection_id)
    entities, relations = await graph_repo.collection_graph(session, collection_id)
    return GraphOut(
        nodes=[
            GraphNode(id=str(e.id), name=e.name, type=e.type, description=e.description)
            for e in entities
        ],
        edges=[
            GraphEdge(
                id=str(r.id),
                source=str(r.source_id),
                target=str(r.target_id),
                relation=r.relation,
                weight=r.weight,
            )
            for r in relations
        ],
    )


@router.post("/documents/{document_id}/extract", response_model=OkResponse)
async def trigger_extraction(document_id: uuid.UUID, session: DbSession) -> OkResponse:
    from app.repositories import documents as document_repo

    await document_repo.get_document(session, document_id)
    await enqueue("extract_graph", document_id=str(document_id))
    return OkResponse()
