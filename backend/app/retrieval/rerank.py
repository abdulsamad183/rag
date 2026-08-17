from __future__ import annotations

from app.reranking.base import Reranker
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy


class RerankedRetrieval(RetrievalStrategy):
    """Wraps any strategy with a second-stage reranker:
    pool (20–50 candidates) → reranker → top evidence chunks."""

    name = "reranked"

    def __init__(self, inner: RetrievalStrategy, reranker: Reranker):
        self.inner = inner
        self.reranker = reranker
        self.name = f"reranked_{inner.name}"

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        result = await self.inner.retrieve(query, context)
        with context.trace.step(
            "rerank", reranker=self.reranker.name, pool=len(result.chunks)
        ) as step:
            reranked = await self.reranker.rerank(query.text, result.chunks, context.top_k)
            step.payload["kept"] = len(reranked)
        return RetrievalResult(
            chunks=reranked,
            strategy=self.name,
            queries_used=result.queries_used,
            hops=result.hops,
            notes=result.notes + [f"reranked with {self.reranker.name}"],
        )
