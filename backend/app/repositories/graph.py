"""Knowledge-graph persistence and traversal (relational implementation).

All graph access goes through this module so a future migration to a graph
database only replaces these functions.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EntityMention, GraphEntity, GraphRelation


def normalize_entity_name(name: str) -> str:
    return " ".join(name.lower().split())[:300]


async def upsert_entity(
    session: AsyncSession,
    collection_id: uuid.UUID,
    name: str,
    entity_type: str,
    description: str = "",
) -> GraphEntity:
    normalized = normalize_entity_name(name)
    stmt = (
        pg_insert(GraphEntity)
        .values(
            collection_id=collection_id,
            name=name[:300],
            normalized_name=normalized,
            type=entity_type,
            description=description[:2000],
        )
        .on_conflict_do_update(
            constraint="uq_entity_identity",
            set_={"description": func.coalesce(GraphEntity.description, description[:2000])},
        )
        .returning(GraphEntity)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def add_relation(
    session: AsyncSession,
    collection_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation: str,
    chunk_id: uuid.UUID | None = None,
) -> None:
    existing = await session.execute(
        select(GraphRelation.id)
        .where(GraphRelation.source_id == source_id)
        .where(GraphRelation.target_id == target_id)
        .where(GraphRelation.relation == relation)
        .limit(1)
    )
    row = existing.first()
    if row:
        await session.execute(
            GraphRelation.__table__.update()
            .where(GraphRelation.id == row[0])
            .values(weight=GraphRelation.weight + 1.0)
        )
        return
    session.add(
        GraphRelation(
            collection_id=collection_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            chunk_id=chunk_id,
        )
    )


async def add_mention(
    session: AsyncSession,
    entity_id: uuid.UUID,
    chunk_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    stmt = (
        pg_insert(EntityMention)
        .values(entity_id=entity_id, chunk_id=chunk_id, document_id=document_id)
        .on_conflict_do_nothing(constraint="uq_mention_entity_chunk")
    )
    await session.execute(stmt)


async def find_entities_matching(
    session: AsyncSession,
    collection_ids: list[uuid.UUID],
    terms: list[str],
    limit: int = 10,
) -> list[GraphEntity]:
    if not terms:
        return []
    conditions = [
        GraphEntity.normalized_name.ilike(f"%{normalize_entity_name(t)}%") for t in terms if t.strip()
    ]
    if not conditions:
        return []
    stmt = (
        select(GraphEntity)
        .where(GraphEntity.collection_id.in_(collection_ids))
        .where(or_(*conditions))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def expand_neighbors(
    session: AsyncSession,
    entity_ids: list[uuid.UUID],
    relation_filter: list[str] | None = None,
    limit: int = 50,
) -> list[GraphRelation]:
    if not entity_ids:
        return []
    stmt = select(GraphRelation).where(
        or_(GraphRelation.source_id.in_(entity_ids), GraphRelation.target_id.in_(entity_ids))
    )
    if relation_filter:
        stmt = stmt.where(GraphRelation.relation.in_(relation_filter))
    stmt = stmt.order_by(GraphRelation.weight.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def chunks_mentioning(
    session: AsyncSession, entity_ids: list[uuid.UUID], limit: int = 40
) -> dict[uuid.UUID, int]:
    """chunk_id -> number of matched entities mentioned (evidence density)."""
    if not entity_ids:
        return {}
    stmt = (
        select(EntityMention.chunk_id, func.count(EntityMention.entity_id))
        .where(EntityMention.entity_id.in_(entity_ids))
        .group_by(EntityMention.chunk_id)
        .order_by(func.count(EntityMention.entity_id).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: int(row[1]) for row in rows}


async def get_entities_by_ids(
    session: AsyncSession, entity_ids: list[uuid.UUID]
) -> list[GraphEntity]:
    if not entity_ids:
        return []
    stmt = select(GraphEntity).where(GraphEntity.id.in_(entity_ids))
    return list((await session.execute(stmt)).scalars().all())


async def collection_graph(
    session: AsyncSession, collection_id: uuid.UUID, limit_entities: int = 150
) -> tuple[list[GraphEntity], list[GraphRelation]]:
    entities = list(
        (
            await session.execute(
                select(GraphEntity)
                .where(GraphEntity.collection_id == collection_id)
                .order_by(GraphEntity.created_at)
                .limit(limit_entities)
            )
        ).scalars()
    )
    ids = [e.id for e in entities]
    relations: list[GraphRelation] = []
    if ids:
        relations = list(
            (
                await session.execute(
                    select(GraphRelation)
                    .where(GraphRelation.collection_id == collection_id)
                    .where(GraphRelation.source_id.in_(ids))
                    .where(GraphRelation.target_id.in_(ids))
                )
            ).scalars()
        )
    return entities, relations


async def delete_collection_graph(session: AsyncSession, collection_id: uuid.UUID) -> None:
    await session.execute(delete(GraphRelation).where(GraphRelation.collection_id == collection_id))
    await session.execute(delete(GraphEntity).where(GraphEntity.collection_id == collection_id))
