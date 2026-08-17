from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid

ENTITY_TYPES = (
    "person", "organization", "paper", "model", "dataset",
    "technology", "product", "concept", "metric",
)

RELATION_TYPES = (
    "AUTHORED_BY", "USES", "DEPENDS_ON", "CITES", "IMPLEMENTS",
    "EVALUATED_ON", "IMPROVES", "EXTENDS", "RELATED_TO",
)


class GraphEntity(Base, TimestampMixin):
    """Knowledge-graph node, stored relationally for now.

    The graph layer is abstracted behind repositories/graph.py so a move to a
    dedicated graph database later only swaps the repository implementation.
    """

    __tablename__ = "graph_entities"
    __table_args__ = (
        UniqueConstraint("collection_id", "normalized_name", "type", name="uq_entity_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class GraphRelation(Base, TimestampMixin):
    __tablename__ = "graph_relations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(40), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class EntityMention(Base, TimestampMixin):
    """Provenance: which chunks mention which entities (drives graph retrieval)."""

    __tablename__ = "entity_mentions"
    __table_args__ = (UniqueConstraint("entity_id", "chunk_id", name="uq_mention_entity_chunk"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
