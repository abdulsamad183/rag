from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class DocumentStatus:
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"

    ALL = (QUEUED, PARSING, CHUNKING, EMBEDDING, INDEXING, COMPLETED, FAILED)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(512), default="")
    source_type: Mapped[str] = mapped_column(String(20))  # pdf|txt|markdown|docx|html|csv|json
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    storage_path: Mapped[str] = mapped_column(String(1024))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    current_version: Mapped[int] = mapped_column(default=1)

    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.QUEUED, index=True)
    progress: Mapped[float] = mapped_column(default=0.0)  # 0..1
    error: Mapped[str] = mapped_column(Text, default="")

    page_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)

    # typed-but-flexible metadata (author, tags, url, table info, code info…)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # temporal validity (Temporal RAG)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # source trust (0..1), inspectable and configurable — never LLM-invented
    trust: Mapped[float] = mapped_column(default=0.6)


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_docver_document_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
