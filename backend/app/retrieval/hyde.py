from __future__ import annotations

from app.core.errors import EmbeddingMismatchError
from app.rag.rewriter import hyde_passage
from app.repositories import chunks as chunk_repo
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import deduplicate, reciprocal_rank_fusion


class HyDERetrieval(RetrievalStrategy):
    """Hypothetical Document Embeddings: retrieve with the embedding of an
    LLM-drafted hypothetical answer, merged with plain query retrieval so a
    bad hypothesis can't sink recall."""

    name = "hyde"

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        if context.embedder is None:
            raise EmbeddingMismatchError("No embedder bound to retrieval context")

        passage = ""
        if context.llm is not None:
            passage = await hyde_passage(context.llm, query.text, context.trace)

        with context.trace.step("retrieve.hyde", generated=bool(passage)) as step:
            texts = [query.text] + ([passage] if passage else [])
            vectors, stats = await context.embedder.embed(texts)
            context.trace.add_embedding_usage(stats.prompt_tokens)

            plain = await chunk_repo.search_vector(
                context.session, context.collection_ids, vectors[0],
                limit=context.pool_size, filters=query.filters,
            )
            lists = [plain]
            if passage:
                hypothetical = await chunk_repo.search_vector(
                    context.session, context.collection_ids, vectors[1],
                    limit=context.pool_size, filters=query.filters,
                )
                lists.append(hypothetical)
            fused = deduplicate(reciprocal_rank_fusion(lists))
            step.payload["candidates"] = len(fused)

        return RetrievalResult(
            chunks=fused[: context.pool_size],
            strategy=self.name,
            queries_used=[query.text],
            notes=["hyde passage used" if passage else "hyde passage unavailable; plain vector"],
        )
