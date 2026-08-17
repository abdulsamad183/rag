from __future__ import annotations

from app.repositories import chunks as chunk_repo
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import normalize_scores


class KeywordRetrieval(RetrievalStrategy):
    """PostgreSQL full-text retrieval (websearch_to_tsquery + ts_rank_cd).
    Essential for exact names, IDs, acronyms, error codes, and numbers that
    embeddings blur."""

    name = "keyword"

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        with context.trace.step("retrieve.keyword", query=query.text[:300]) as step:
            results = await chunk_repo.search_keyword(
                context.session,
                context.collection_ids,
                query.text,
                limit=context.pool_size,
                filters=query.filters,
            )
            normalize_scores(results, "keyword")
            for chunk in results:
                chunk.score = chunk.scores["keyword"]
            step.payload["candidates"] = len(results)
        return RetrievalResult(chunks=results, strategy=self.name, queries_used=[query.text])
