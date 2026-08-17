from app.config.profiles import PROFILES
from app.rag.query_analysis import deterministic_analysis
from app.rag.router import route


def test_deterministic_analysis_simple():
    analysis = deterministic_analysis("What is Aurora?")
    assert analysis["query_type"] == "simple_fact"
    assert analysis["complexity"] == "low"


def test_deterministic_analysis_comparison():
    analysis = deterministic_analysis("Compare the 2024 and 2025 benchmark results")
    assert analysis["query_type"] == "comparison"


def test_deterministic_analysis_temporal():
    analysis = deterministic_analysis("What was the retention policy in 2024?")
    assert analysis["query_type"] == "temporal"
    assert "2024" in analysis["time_constraints"]


def test_deterministic_analysis_acronyms_as_entities():
    analysis = deterministic_analysis("How does HNSW indexing work?")
    assert "HNSW" in analysis["entities"]


def test_router_simple_goes_hybrid():
    decision = route(deterministic_analysis("What is Aurora?"), PROFILES["adaptive"], False)
    assert decision.strategy == "hybrid"


def test_router_temporal():
    analysis = deterministic_analysis("What was the retention policy in 2024?")
    decision = route(analysis, PROFILES["adaptive"], False)
    assert decision.strategy == "temporal"


def test_router_comparison_multi_query():
    analysis = deterministic_analysis("Compare HNSW versus IVF indexes")
    decision = route(analysis, PROFILES["adaptive"], False)
    assert decision.strategy == "multi_query"


def test_router_relationship_needs_graph():
    analysis = {"query_type": "relationship", "complexity": "medium"}
    with_graph = route(analysis, PROFILES["adaptive"], True)
    without_graph = route(analysis, PROFILES["adaptive"], False)
    assert with_graph.strategy == "graph"
    assert without_graph.strategy != "graph"


def test_router_fast_profile_pins_strategy():
    profile = PROFILES["fast"]
    analysis = deterministic_analysis("Compare A versus B in 2024 and 2025")
    decision = route(analysis, profile, True)
    assert decision.strategy == profile.default_strategy


def test_router_lookup_boosts_keyword_weight():
    analysis = deterministic_analysis('Find the exact error code "AUR-1002"')
    decision = route(analysis, PROFILES["adaptive"], False)
    assert decision.strategy == "hybrid"
    assert decision.params.get("keyword_weight", 0) > decision.params.get("semantic_weight", 1)


def test_all_profiles_exist():
    for name in ("fast", "balanced", "adaptive", "deep", "research"):
        assert name in PROFILES
