from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.hybrid import HybridRetrieval
from app.utils.text import extract_years


class TemporalRetrieval(RetrievalStrategy):
    """Time-aware retrieval.

    Deterministically extracts time constraints (query analysis first, regex
    fallback), applies validity-window SQL filters, and prefers temporally
    valid evidence over merely newest documents by boosting in-window results.
    """

    name = "temporal"
    IN_WINDOW_BOOST = 0.15

    def __init__(self, inner: RetrievalStrategy | None = None):
        self.inner = inner or HybridRetrieval()

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        years = [
            int(y) for y in query.analysis.get("time_constraints", []) if str(y).isdigit()
        ] or extract_years(query.text)

        filters = query.filters
        notes: list[str] = []
        if years:
            target = datetime(min(years), 7, 1, tzinfo=UTC)
            filters = replace(query.filters, valid_at=target)
            notes.append(f"temporal filter: valid at {target.date().isoformat()}")
        context.trace.add_step("temporal.constraints", years=years)

        result = await self.inner.retrieve(replace(query, filters=filters), context)

        if years:
            low, high = min(years), max(years)
            for chunk in result.chunks:
                published = chunk.meta.get("published_at")
                if published:
                    try:
                        year = int(str(published)[:4])
                        if low <= year <= high + (0 if low != high else 0):
                            chunk.score += self.IN_WINDOW_BOOST
                            chunk.scores["temporal_boost"] = self.IN_WINDOW_BOOST
                    except ValueError:
                        pass
            result.chunks.sort(key=lambda c: c.score, reverse=True)

        return RetrievalResult(
            chunks=result.chunks,
            strategy=self.name,
            queries_used=result.queries_used,
            notes=result.notes + notes,
        )
