"""Retrieval strategy interface and shared data structures."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.tracing import TraceRecorder

if TYPE_CHECKING:
    from app.embeddings.registry import CachingEmbedder
    from app.llm.base import LLMProvider
    from app.models import Collection


@dataclass
class QueryFilters:
    """Deterministic metadata filters applied inside SQL."""

    document_ids: list[uuid.UUID] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    author: str = ""
    valid_at: datetime | None = None        # temporal point ("policy in 2024")
    valid_range: tuple[datetime, datetime] | None = None
    section: str = ""

    def is_empty(self) -> bool:
        return not any(
            [self.document_ids, self.source_types, self.tags, self.author,
             self.valid_at, self.valid_range, self.section]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_ids": [str(d) for d in self.document_ids],
            "source_types": self.source_types,
            "tags": self.tags,
            "author": self.author,
            "valid_at": self.valid_at.isoformat() if self.valid_at else None,
            "section": self.section,
        }


@dataclass
class Query:
    text: str
    filters: QueryFilters = field(default_factory=QueryFilters)
    analysis: dict[str, Any] = field(default_factory=dict)  # query-understanding output


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    score: float = 0.0                     # final (fused/reranked) score, higher is better
    scores: dict[str, float] = field(default_factory=dict)  # per-source: vector/keyword/rerank/graph
    document_name: str = ""
    source_type: str = ""
    heading: str = ""
    section_path: str = ""
    page_start: int | None = None
    page_end: int | None = None
    level: str = "chunk"
    parent_id: uuid.UUID | None = None
    trust: float = 0.6
    meta: dict[str, Any] = field(default_factory=dict)

    def as_trace_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "document_name": self.document_name,
            "score": round(self.score, 4),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "page": self.page_start,
            "section": self.section_path or self.heading,
            "preview": self.content[:160],
        }


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    strategy: str
    queries_used: list[str] = field(default_factory=list)
    hops: int = 0
    notes: list[str] = field(default_factory=list)  # safe, structured decisions for the trace


@dataclass
class RetrievalContext:
    session: AsyncSession
    collections: list[Collection]
    trace: TraceRecorder
    top_k: int = 10
    pool_size: int = 30
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3
    llm: LLMProvider | None = None          # for strategies that rewrite/plan
    embedder: CachingEmbedder | None = None  # bound to the collections' embedding space
    max_hops: int = 3
    multi_query_count: int = 3

    @property
    def collection_ids(self) -> list[uuid.UUID]:
        return [c.id for c in self.collections]


class RetrievalStrategy(ABC):
    name: str = ""

    @abstractmethod
    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult: ...
