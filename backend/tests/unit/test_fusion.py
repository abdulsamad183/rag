import uuid

from app.retrieval.base import RetrievedChunk
from app.retrieval.fusion import (
    deduplicate,
    normalize_scores,
    reciprocal_rank_fusion,
    weighted_fusion,
)


def make_chunk(name: str, score: float, source: str = "vector") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        document_id=uuid.uuid4(),
        content=f"content of {name}",
        score=score,
        scores={source: score},
    )


def test_normalize_scores_minmax():
    chunks = [make_chunk("a", 2.0), make_chunk("b", 4.0), make_chunk("c", 6.0)]
    normalize_scores(chunks, "vector")
    values = [c.scores["vector"] for c in chunks]
    assert values == [0.0, 0.5, 1.0]


def test_normalize_scores_equal_values():
    chunks = [make_chunk("a", 3.0), make_chunk("b", 3.0)]
    normalize_scores(chunks, "vector")
    assert all(c.scores["vector"] == 1.0 for c in chunks)


def test_rrf_prefers_items_in_both_lists():
    shared = make_chunk("shared", 0.9)
    shared_kw = make_chunk("shared", 0.5, source="keyword")
    only_vector = make_chunk("only-vector", 0.99)
    only_keyword = make_chunk("only-keyword", 0.8, source="keyword")

    fused = reciprocal_rank_fusion([[only_vector, shared], [shared_kw, only_keyword]], k=60)
    assert str(fused[0].chunk_id) == str(shared.chunk_id)
    assert "rrf" in fused[0].scores
    # merged chunk carries both source scores
    assert "vector" in fused[0].scores and "keyword" in fused[0].scores


def test_weighted_fusion_weights_matter():
    vector_hit = make_chunk("vec", 1.0)
    keyword_hit = make_chunk("kw", 1.0, source="keyword")

    keyword_heavy = weighted_fusion([vector_hit], [keyword_hit],
                                    semantic_weight=0.1, keyword_weight=0.9)
    assert str(keyword_heavy[0].chunk_id) == str(keyword_hit.chunk_id)


def test_deduplicate_by_id_and_content():
    a1 = make_chunk("a", 0.9)
    a2 = make_chunk("a", 0.5)  # same deterministic id
    b = make_chunk("b", 0.7)
    b_copy = make_chunk("b2", 0.6)
    b_copy.content = b.content  # same content, different id

    result = deduplicate([a1, a2, b, b_copy])
    assert len(result) == 2
    assert result[0].score == 0.9  # kept the best-scoring duplicate
