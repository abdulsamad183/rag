from __future__ import annotations

import asyncio

from app.core.errors import EmbeddingMismatchError
from app.repositories import chunks as chunk_repo
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import reciprocal_rank_fusion, weighted_fusion


class HybridRetrieval(RetrievalStrategy):
    """Vector + keyword search in parallel, fused with configurable weights
    (weighted linear) or RRF."""

    name = "hybrid"

    def __init__(self, fusion: str = "weighted"):
        self.fusion = fusion

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        if context.embedder is None:
            raise EmbeddingMismatchError("No embedder bound to retrieval context")
        with context.trace.step(
            "retrieve.hybrid", query=query.text[:300], fusion=self.fusion,
            semantic_weight=context.semantic_weight, keyword_weight=context.keyword_weight,
        ) as step:
            vectors, stats = await context.embedder.embed([query.text])
            context.trace.add_embedding_usage(stats.prompt_tokens)
            vector_task = chunk_repo.search_vector(
                context.session, context.collection_ids, vectors[0],
                limit=context.pool_size, filters=query.filters,
            )
            keyword_task = chunk_repo.search_keyword(
                context.session, context.collection_ids, query.text,
                limit=context.pool_size, filters=query.filters,
            )
            vector_results, keyword_results = await asyncio.gather(vector_task, keyword_task)

            if self.fusion == "rrf":
                fused = reciprocal_rank_fusion([vector_results, keyword_results])
            else:
                fused = weighted_fusion(
                    vector_results, keyword_results,
                    context.semantic_weight, context.keyword_weight,
                )
            step.payload.update(
                vector_candidates=len(vector_results),
                keyword_candidates=len(keyword_results),
                fused=len(fused),
            )
        return RetrievalResult(
            chunks=fused[: context.pool_size], strategy=self.name, queries_used=[query.text]
        )
