from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TraceSummary(BaseModel):
    id: uuid.UUID
    request_id: str
    query: str
    mode: str
    strategy: str
    provider: str
    model: str
    abstained: bool
    latency_ms: int
    created_at: datetime
    confidence: dict[str, Any] = {}

    model_config = {"from_attributes": True}


class TraceOut(TraceSummary):
    conversation_id: uuid.UUID | None
    query_analysis: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    retrieved: list[dict[str, Any]] = []
    verification: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    collection_ids: list[str] = Field(default_factory=list)
    answer: str = ""
    error: str = ""


class LatencyStats(BaseModel):
    mean: float = 0.0
    p50: float = 0.0
    p95: float = 0.0


class TotalsStats(BaseModel):
    queries: int = 0
    abstain_rate: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: LatencyStats = Field(default_factory=LatencyStats)


class ProviderStats(BaseModel):
    provider: str
    queries: int = 0
    estimated_cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0
    abstain_rate: float = 0.0


class CollectionStats(BaseModel):
    collection_id: str
    queries: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0
    abstain_rate: float = 0.0


class RetrievalStatsOut(BaseModel):
    days: int
    totals: TotalsStats
    by_provider: list[ProviderStats] = Field(default_factory=list)
    by_collection: list[CollectionStats] = Field(default_factory=list)
