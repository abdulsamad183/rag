from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(50), index=True)  # ingest|graph_extract|evaluation|reindex
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
