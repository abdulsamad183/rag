from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    collection_ids: list[uuid.UUID] = Field(min_length=1)
    conversation_id: uuid.UUID | None = None
    mode: Literal["fast", "balanced", "adaptive", "deep", "research"] = "adaptive"
    provider: str | None = Field(default=None, description="openai | groq | gemini | ollama")
    model: str | None = None
    # Advanced options
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=64, le=8192)
    max_context_tokens: int | None = Field(default=None, ge=500, le=100_000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank_top_k: int | None = Field(default=None, ge=1, le=30)
    retrieval_strategy: str | None = None
    reranker: Literal["none", "lexical", "llm"] | None = None
    max_hops: int | None = Field(default=None, ge=1, le=5)
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    allow_fallback: bool = False
    scope: Literal["kb", "kb_web", "web"] = "kb"
    debug: bool = False


class CitationOut(BaseModel):
    marker: int
    chunk_id: str
    document_id: str
    document_name: str
    page: int | None = None
    section: str = ""
    snippet: str = ""
    source_url: str = ""
    relevance_score: float = 0.0


class EvidenceOut(BaseModel):
    marker: int
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    score: float
    scores: dict[str, float] = {}
    source_type: str = ""
    page: int | None = None
    section: str = ""
    trust: float = 0.6
    url: str = ""


class ConfidenceOut(BaseModel):
    score: float
    level: str
    signals: dict[str, float] = {}
    weights: dict[str, float] = {}


class VerificationOut(BaseModel):
    claims: list[dict[str, Any]] = []
    supported: int = 0
    total: int = 0
    support_ratio: float = 1.0
    contradictions: list[dict[str, Any]] = []
    error: str = ""


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    trace_id: uuid.UUID
    answer: str
    abstained: bool
    strategy: str
    mode: str
    provider: str
    model: str
    confidence: ConfidenceOut
    citations: list[CitationOut] = []
    evidence: list[EvidenceOut] = []
    verification: VerificationOut | None = None
    queries_used: list[str] = []
    correction_rounds: int = 0
    fallback_used: str = ""
    usage: dict[str, Any] = {}
    latency_ms: int = 0
    debug_steps: list[dict[str, Any]] | None = None
