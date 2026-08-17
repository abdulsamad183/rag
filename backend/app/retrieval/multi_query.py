from __future__ import annotations

import asyncio
from dataclasses import replace

from app.rag.rewriter import expand_query
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import deduplicate, reciprocal_rank_fusion
from app.retrieval.hybrid import HybridRetrieval


class MultiQueryRetrieval(RetrievalStrategy):
    """Query expansion / decomposition → parallel retrieval → RRF merge.

    Uses sub-questions from query analysis when present (decomposition for
    comparisons and multi-part questions), otherwise LLM-generated semantic
    variants. Retrieval runs in parallel with bounded concurrency.
    """

    name = "multi_query"
    MAX_PARALLEL = 4

    def __init__(self, inner: RetrievalStrategy | None = None):
        self.inner = inner or HybridRetrieval()

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        sub_questions = [
            q for q in query.analysis.get("sub_questions", []) if isinstance(q, str) and q.strip()
        ]
        variants: list[str] = []
        if sub_questions:
            variants = sub_questions[: context.multi_query_count + 1]
            source = "decomposition"
        elif context.llm is not None:
            variants = await expand_query(
                context.llm, query.text, context.multi_query_count, context.trace
            )
            source = "expansion"
        else:
            source = "none"

        queries = [query.text] + [v for v in variants if v.lower() != query.text.lower()]
        context.trace.add_step("multi_query.plan", source=source, queries=queries)

        semaphore = asyncio.Semaphore(self.MAX_PARALLEL)

        async def run(text: str) -> RetrievalResult:
            async with semaphore:
                return await self.inner.retrieve(replace(query, text=text), context)

        results = await asyncio.gather(*(run(q) for q in queries), return_exceptions=True)
        result_lists = []
        used: list[str] = []
        for text, result in zip(queries, results, strict=True):
            if isinstance(result, BaseException):
                context.trace.add_step("multi_query.branch_failed", status="error", query=text)
                continue
            result_lists.append(result.chunks)
            used.append(text)

        fused = deduplicate(reciprocal_rank_fusion(result_lists))
        return RetrievalResult(
            chunks=fused[: context.pool_size],
            strategy=self.name,
            queries_used=used,
            notes=[f"{len(used)} queries via {source}"],
        )
