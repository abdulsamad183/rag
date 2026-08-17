"""Execution profiles: bundles of pipeline behavior per chat mode.

fast      — Mode A (simple RAG): single retrieval, no verification.
balanced  — hybrid + rerank, no claim verification.
adaptive  — Mode B: router decides strategy; verification when complexity demands.
deep      — Mode C-lite: decomposition/multi-hop + verification + self-correction.
research  — Mode C: deep + graph/temporal awareness + contradiction analysis.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    use_llm_query_analysis: bool
    allow_multi_query: bool
    allow_multi_hop: bool
    allow_graph: bool
    allow_temporal: bool
    use_reranker: bool
    verify_claims: bool
    max_correction_rounds: int
    detect_contradictions: bool
    default_strategy: str  # "auto" lets the router decide


PROFILES: dict[str, Profile] = {
    "fast": Profile(
        name="fast",
        use_llm_query_analysis=False,
        allow_multi_query=False,
        allow_multi_hop=False,
        allow_graph=False,
        allow_temporal=False,
        use_reranker=False,
        verify_claims=False,
        max_correction_rounds=0,
        detect_contradictions=False,
        default_strategy="vector",
    ),
    "balanced": Profile(
        name="balanced",
        use_llm_query_analysis=False,
        allow_multi_query=False,
        allow_multi_hop=False,
        allow_graph=False,
        allow_temporal=True,
        use_reranker=True,
        verify_claims=False,
        max_correction_rounds=0,
        detect_contradictions=False,
        default_strategy="hybrid",
    ),
    "adaptive": Profile(
        name="adaptive",
        use_llm_query_analysis=True,
        allow_multi_query=True,
        allow_multi_hop=True,
        allow_graph=True,
        allow_temporal=True,
        use_reranker=True,
        verify_claims=True,
        max_correction_rounds=1,
        detect_contradictions=False,
        default_strategy="auto",
    ),
    "deep": Profile(
        name="deep",
        use_llm_query_analysis=True,
        allow_multi_query=True,
        allow_multi_hop=True,
        allow_graph=False,
        allow_temporal=True,
        use_reranker=True,
        verify_claims=True,
        max_correction_rounds=1,
        detect_contradictions=True,
        default_strategy="auto",
    ),
    "research": Profile(
        name="research",
        use_llm_query_analysis=True,
        allow_multi_query=True,
        allow_multi_hop=True,
        allow_graph=True,
        allow_temporal=True,
        use_reranker=True,
        verify_claims=True,
        max_correction_rounds=2,
        detect_contradictions=True,
        default_strategy="auto",
    ),
}


def get_profile(name: str) -> Profile:
    return PROFILES.get(name, PROFILES["adaptive"])
