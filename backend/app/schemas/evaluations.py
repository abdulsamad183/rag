from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    question_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionOut(BaseModel):
    id: uuid.UUID
    question: str
    expected_answer: str
    relevant_documents: list[str]
    relevant_chunks: list[str]
    question_type: str
    answerable: bool

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    name: str = Field(default="", max_length=300)
    collection_ids: list[uuid.UUID] = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    mode: str = "balanced"
    strategy: str | None = None
    top_k: int | None = None
    rerank_top_k: int | None = None
    reranker: str | None = None
    k: int = Field(default=5, ge=1, le=20, description="K for retrieval metrics")
    use_llm_judge: bool = False


class RunOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    name: str
    config: dict[str, Any]
    status: str
    progress: float
    metrics: dict[str, Any]
    error: str
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ResultOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    answer: str
    abstained: bool
    retrieved: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    metrics: dict[str, Any]
    failure_category: str
    latency_ms: int
    error: str
    trace_id: uuid.UUID | None = None
    question: str = ""
    expected_answer: str = ""
    question_type: str = ""
    answerable: bool = True

    model_config = {"from_attributes": True}


class RunComparison(BaseModel):
    runs: list[RunOut]
    metric_table: dict[str, dict[str, float | None]]  # metric -> run_id -> value
