from __future__ import annotations

from app.core.errors import EmbeddingMismatchError
from app.repositories import chunks as chunk_repo
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy


class VectorRetrieval(RetrievalStrategy):
    name = "vector"

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        if context.embedder is None:
            raise EmbeddingMismatchError("No embedder bound to retrieval context")
        with context.trace.step("retrieve.vector", query=query.text[:300]) as step:
            vectors, stats = await context.embedder.embed([query.text])
            context.trace.add_embedding_usage(stats.prompt_tokens)
            results = await chunk_repo.search_vector(
                context.session,
                context.collection_ids,
                vectors[0],
                limit=context.pool_size,
                filters=query.filters,
            )
            step.payload["candidates"] = len(results)
        return RetrievalResult(chunks=results, strategy=self.name, queries_used=[query.text])
