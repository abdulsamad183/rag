from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    collection_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")  # rolling summary memory


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("retrieval_traces.id", ondelete="SET NULL"), nullable=True
    )
    # confidence, strategy, usage, abstained, verification summary
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Citation(Base, TimestampMixin):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    marker: Mapped[int] = mapped_column(default=0)  # [1], [2]…
    document_name: Mapped[str] = mapped_column(String(512), default="")
    page: Mapped[int | None] = mapped_column(nullable=True)
    section: Mapped[str] = mapped_column(String(1024), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(2048), default="")
    relevance_score: Mapped[float] = mapped_column(default=0.0)
