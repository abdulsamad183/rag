from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class ChunkLevel:
    DOCUMENT = "document"
    SECTION = "section"   # parent chunks / hierarchy nodes
    CHUNK = "chunk"       # leaf retrieval units


class Chunk(Base, TimestampMixin):
    """Indexed retrieval unit.

    - ``embedding`` uses an untyped pgvector column so collections may use
      different embedding dimensions; per-dimension partial HNSW indexes are
      created at index time (see services/indexing.py).
    - ``tsv`` is a stored generated column powering keyword (full-text) search.
    - ``parent_id`` links child chunks to parent/section chunks
      (parent-child + hierarchical retrieval).
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_collection_level", "collection_id", "level"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_meta", "meta", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    level: Mapped[str] = mapped_column(String(20), default=ChunkLevel.CHUNK)
    chunk_index: Mapped[int] = mapped_column(default=0)
    doc_version: Mapped[int] = mapped_column(default=1)

    heading: Mapped[str] = mapped_column(String(512), default="")
    section_path: Mapped[str] = mapped_column(String(1024), default="")  # "Ch 2 > Methods > Setup"
    page_start: Mapped[int | None] = mapped_column(nullable=True)
    page_end: Mapped[int | None] = mapped_column(nullable=True)

    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_count: Mapped[int] = mapped_column(default=0)
    summary: Mapped[str] = mapped_column(Text, default="")

    embedding: Mapped[Any | None] = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(200), default="")

    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', left(content, 100000))", persisted=True),
        nullable=True,
    )
