from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
    answer: str = ""
    error: str = ""
