from __future__ import annotations

from app.config.profiles import Profile
from app.rag.router import RouteDecision, route
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy


class AdaptiveRetrieval(RetrievalStrategy):
    """Adaptive RAG: classify → route → delegate.

    The routing decision (and its reason) is always recorded in the trace so
    strategy selection stays auditable.
    """

    name = "adaptive"

    def __init__(self, profile: Profile, strategies: dict[str, RetrievalStrategy], graph_available: bool):
        self.profile = profile
        self.strategies = strategies
        self.graph_available = graph_available

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        decision: RouteDecision = route(query.analysis, self.profile, self.graph_available)
        context.trace.add_step(
            "router",
            strategy=decision.strategy,
            reason=decision.reason,
            params=decision.params,
        )
        if "semantic_weight" in decision.params:
            context.semantic_weight = decision.params["semantic_weight"]
        if "keyword_weight" in decision.params:
            context.keyword_weight = decision.params["keyword_weight"]

        strategy = self.strategies.get(decision.strategy) or self.strategies["hybrid"]
        result = await strategy.retrieve(query, context)
        return RetrievalResult(
            chunks=result.chunks,
            strategy=f"adaptive:{result.strategy}",
            queries_used=result.queries_used,
            hops=result.hops,
            notes=[f"routed to {decision.strategy}: {decision.reason}"] + result.notes,
        )
