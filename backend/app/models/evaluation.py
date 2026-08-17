from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class EvaluationDataset(Base, TimestampMixin):
    __tablename__ = "evaluation_datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    question_count: Mapped[int] = mapped_column(default=0)


class EvaluationQuestion(Base, TimestampMixin):
    __tablename__ = "evaluation_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str] = mapped_column(Text, default="")
    # ground-truth references: document filenames/titles and/or chunk content probes
    relevant_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    relevant_chunks: Mapped[list[str]] = mapped_column(JSONB, default=list)
    question_type: Mapped[str] = mapped_column(String(40), default="simple")
    answerable: Mapped[bool] = mapped_column(default=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class EvaluationRun(Base, TimestampMixin):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), default="")
    # experiment record: provider, model, strategy, chunking, prompts versions…
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(default=0.0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationResult(Base, TimestampMixin):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_questions.id", ondelete="CASCADE"), index=True
    )
    answer: Mapped[str] = mapped_column(Text, default="")
    abstained: Mapped[bool] = mapped_column(default=False)
    retrieved: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    failure_category: Mapped[str] = mapped_column(String(50), default="")
    trace_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(Text, default="")
