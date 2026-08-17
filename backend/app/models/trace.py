from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class RetrievalTrace(Base, TimestampMixin):
    """Full structured record of one RAG execution.

    ``steps`` holds ordered pipeline events (name, status, latency_ms, safe
    payload). No private chain-of-thought is stored — only structured system
    events, scores, and decisions.
    """

    __tablename__ = "retrieval_traces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    request_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    query: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(30), default="")
    strategy: Mapped[str] = mapped_column(String(50), default="", index=True)
    provider: Mapped[str] = mapped_column(String(30), default="")
    model: Mapped[str] = mapped_column(String(200), default="")

    query_analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    retrieved: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    verification: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # tokens, cost, per-step latency

    answer: Mapped[str] = mapped_column(Text, default="")
    abstained: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(default=0)
