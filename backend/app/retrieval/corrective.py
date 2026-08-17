from __future__ import annotations

from dataclasses import replace

from app.rag.rewriter import expand_query
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import deduplicate, reciprocal_rank_fusion
from app.retrieval.hybrid import HybridRetrieval
from app.utils.text import term_coverage


class CorrectiveRetrieval(RetrievalStrategy):
    """Corrective RAG: retrieve → evaluate quality deterministically →
    if weak, rewrite the query and retrieve again (one correction pass).

    Quality check is deterministic (score levels + query-term coverage), so
    the correction trigger is cheap and predictable.
    """

    name = "corrective"
    MIN_MEAN_COVERAGE = 0.35
    MIN_CANDIDATES = 3

    def __init__(self, inner: RetrievalStrategy | None = None):
        self.inner = inner or HybridRetrieval()

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        first = await self.inner.retrieve(query, context)
        top = first.chunks[: context.top_k]
        coverage = (
            sum(term_coverage(query.text, c.content) for c in top) / len(top) if top else 0.0
        )
        weak = len(top) < self.MIN_CANDIDATES or coverage < self.MIN_MEAN_COVERAGE
        context.trace.add_step(
            "corrective.evaluate",
            candidates=len(top),
            mean_term_coverage=round(coverage, 3),
            correction_triggered=weak,
        )
        if not weak or context.llm is None:
            return first

        variants = await expand_query(context.llm, query.text, 2, context.trace)
        if not variants:
            return first

        lists = [first.chunks]
        used = list(first.queries_used)
        for variant in variants:
            retry = await self.inner.retrieve(replace(query, text=variant), context)
            lists.append(retry.chunks)
            used.append(variant)

        fused = deduplicate(reciprocal_rank_fusion(lists))
        return RetrievalResult(
            chunks=fused[: context.pool_size],
            strategy=self.name,
            queries_used=used,
            notes=first.notes + [f"correction pass with {len(variants)} rewrites"],
        )
