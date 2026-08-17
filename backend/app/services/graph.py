"""Knowledge-graph extraction: LLM-driven entity/relation mining over a
document's chunks, persisted through the graph repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.base import ChatMessage, GenerationParams
from app.llm.registry import get_llm
from app.models import Chunk, ChunkLevel
from app.models.graph import ENTITY_TYPES, RELATION_TYPES
from app.rag import prompts
from app.repositories import documents as document_repo
from app.repositories import graph as graph_repo

logger = get_logger("graph")

MAX_CHUNKS_PER_DOCUMENT = 40


async def extract_document_graph(
    session: AsyncSession, document_id: uuid.UUID, provider: str | None = None, model: str | None = None
) -> dict[str, int]:
    document = await document_repo.get_document(session, document_id)
    llm = get_llm(provider, model)

    stmt = (
        select(Chunk)
        .where(Chunk.document_id == document_id, Chunk.level == ChunkLevel.CHUNK)
        .order_by(Chunk.chunk_index)
        .limit(MAX_CHUNKS_PER_DOCUMENT)
    )
    chunks = list((await session.execute(stmt)).scalars().all())

    entities_created = 0
    relations_created = 0
    for chunk in chunks:
        try:
            result = await llm.structured_output(
                [
                    ChatMessage(role="system", content=prompts.ENTITY_EXTRACTOR_SYSTEM),
                    ChatMessage(
                        role="user",
                        content=prompts.ENTITY_EXTRACTOR_USER.format(text=chunk.content[:4000]),
                    ),
                ],
                schema_hint=prompts.ENTITY_EXTRACTOR_SCHEMA,
                params=GenerationParams(temperature=0.0, max_tokens=800),
            )
        except Exception as exc:  # noqa: BLE001 — one bad chunk must not kill the job
            logger.warning("graph_chunk_failed", chunk_id=str(chunk.id), error=str(exc)[:150])
            continue

        name_to_id: dict[str, uuid.UUID] = {}
        for raw in result.get("entities", []):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            entity_type = str(raw.get("type", "concept")).lower().strip()
            if not name or entity_type not in ENTITY_TYPES:
                continue
            entity = await graph_repo.upsert_entity(
                session, document.collection_id, name, entity_type,
                str(raw.get("description", ""))[:500],
            )
            name_to_id[graph_repo.normalize_entity_name(name)] = entity.id
            await graph_repo.add_mention(session, entity.id, chunk.id, document.id)
            entities_created += 1

        for raw in result.get("relations", []):
            if not isinstance(raw, dict):
                continue
            source = name_to_id.get(graph_repo.normalize_entity_name(str(raw.get("source", ""))))
            target = name_to_id.get(graph_repo.normalize_entity_name(str(raw.get("target", ""))))
            relation = str(raw.get("relation", "")).upper().strip()
            if not source or not target or source == target or relation not in RELATION_TYPES:
                continue
            await graph_repo.add_relation(
                session, document.collection_id, source, target, relation, chunk.id
            )
            relations_created += 1

        await session.commit()

    logger.info(
        "graph_extraction_done",
        document_id=str(document_id),
        entities=entities_created,
        relations=relations_created,
    )
    return {"entities": entities_created, "relations": relations_created}
