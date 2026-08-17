"""Deterministic retrieval router.

Rule-based (cheap, predictable, testable) — the LLM contributes only the
query classification it feeds on. The router never invokes the most
expensive pipeline for simple questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config.profiles import Profile


@dataclass
class RouteDecision:
    strategy: str
    reason: str
    params: dict[str, Any] = field(default_factory=dict)  # weight overrides etc.


def route(analysis: dict[str, Any], profile: Profile, graph_available: bool) -> RouteDecision:
    query_type = analysis.get("query_type", "simple_fact")
    complexity = analysis.get("complexity", "low")
    has_subs = bool(analysis.get("sub_questions"))
    has_time = bool(analysis.get("time_constraints"))

    if profile.default_strategy != "auto":
        return RouteDecision(
            strategy=profile.default_strategy,
            reason=f"profile '{profile.name}' pins strategy",
        )

    if has_time and query_type == "temporal" and profile.allow_temporal:
        return RouteDecision(strategy="temporal", reason="explicit time constraints")

    if query_type == "relationship" and profile.allow_graph and graph_available:
        return RouteDecision(strategy="graph", reason="relationship question with graph available")

    if query_type == "multi_hop" and profile.allow_multi_hop:
        return RouteDecision(strategy="multi_hop", reason="multi-hop reasoning required")

    if (query_type == "comparison" or has_subs) and profile.allow_multi_query:
        return RouteDecision(
            strategy="multi_query",
            reason="comparison/decomposable question → parallel sub-queries",
        )

    if query_type == "analytical" and complexity == "high" and profile.allow_multi_hop:
        return RouteDecision(strategy="multi_hop", reason="high-complexity analytical question")

    if query_type == "specific_lookup":
        return RouteDecision(
            strategy="hybrid",
            reason="exact lookup → keyword-weighted hybrid",
            params={"semantic_weight": 0.35, "keyword_weight": 0.65},
        )

    if query_type == "summarization":
        return RouteDecision(
            strategy="multi_query" if profile.allow_multi_query else "hybrid",
            reason="summarization → broad multi-angle retrieval",
        )

    if complexity == "low":
        return RouteDecision(strategy="hybrid", reason="simple question → hybrid fast path")

    return RouteDecision(strategy="hybrid", reason="default hybrid")
