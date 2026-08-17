from __future__ import annotations

from app.config.profiles import Profile
from app.retrieval.adaptive import AdaptiveRetrieval
from app.retrieval.base import RetrievalStrategy
from app.retrieval.corrective import CorrectiveRetrieval
from app.retrieval.graph import GraphRetrieval
from app.retrieval.hybrid import HybridRetrieval
from app.retrieval.hyde import HyDERetrieval
from app.retrieval.keyword import KeywordRetrieval
from app.retrieval.multi_hop import MultiHopRetrieval
from app.retrieval.multi_query import MultiQueryRetrieval
from app.retrieval.temporal import TemporalRetrieval
from app.retrieval.vector import VectorRetrieval

STRATEGY_NAMES = (
    "vector",
    "keyword",
    "hybrid",
    "hybrid_rrf",
    "hyde",
    "multi_query",
    "multi_hop",
    "temporal",
    "graph",
    "corrective",
    "adaptive",
)


def build_strategies() -> dict[str, RetrievalStrategy]:
    hybrid = HybridRetrieval()
    return {
        "vector": VectorRetrieval(),
        "keyword": KeywordRetrieval(),
        "hybrid": hybrid,
        "hybrid_rrf": HybridRetrieval(fusion="rrf"),
        "hyde": HyDERetrieval(),
        "multi_query": MultiQueryRetrieval(inner=hybrid),
        "multi_hop": MultiHopRetrieval(inner=hybrid),
        "temporal": TemporalRetrieval(inner=hybrid),
        "graph": GraphRetrieval(inner=hybrid),
        "corrective": CorrectiveRetrieval(inner=hybrid),
    }


def get_strategy(
    name: str, profile: Profile, graph_available: bool = False
) -> RetrievalStrategy:
    strategies = build_strategies()
    if name == "adaptive" or name == "auto":
        return AdaptiveRetrieval(profile, strategies, graph_available)
    return strategies.get(name) or strategies["hybrid"]
