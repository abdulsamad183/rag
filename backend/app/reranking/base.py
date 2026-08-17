from __future__ import annotations

from abc import ABC, abstractmethod

from app.retrieval.base import RetrievedChunk


class Reranker(ABC):
    """Second-stage relevance scorer applied to the candidate pool.

    Adapters: ``lexical`` (deterministic, zero-cost), ``llm`` (provider-scored).
    A local cross-encoder adapter is a documented extension point
    (docs/rag-strategies.md#reranking) — implement this interface and register
    it in reranking/__init__.py.
    """

    name: str = ""

    @abstractmethod
    async def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        """Return the top_k chunks re-ordered by refined relevance; must set
        chunk.scores['rerank'] and update chunk.score."""


class NoopReranker(Reranker):
    name = "none"

    async def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return chunks[:top_k]
