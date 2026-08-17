from app.evaluation.metrics import (
    categorize_failure,
    citation_metrics,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    retrieval_metrics,
    token_f1,
)


def test_precision_recall_basic():
    flags = [True, False, True, False, False]
    assert precision_at_k(flags, 5) == 0.4
    assert recall_at_k(flags, 5, total_relevant=2) == 1.0
    assert recall_at_k(flags, 1, total_relevant=2) == 0.5


def test_mrr_first_hit_position():
    assert mrr([False, True, False]) == 0.5
    assert mrr([True]) == 1.0
    assert mrr([False, False]) == 0.0


def test_ndcg_perfect_ranking_is_one():
    assert ndcg_at_k([True, True, False, False], 4) == 1.0
    assert 0 < ndcg_at_k([False, True, True, False], 4) < 1.0


def test_token_f1():
    assert token_f1("the answer is 42", "the answer is 42") == 1.0
    assert token_f1("something else entirely", "the answer is 42") == 0.0
    assert 0 < token_f1("the answer is roughly 42", "the answer is 42") < 1.0


def test_retrieval_metrics_content_probes():
    retrieved = [
        {"content": "snapshots are kept for 30 days", "document_name": "report-2024.md"},
        {"content": "irrelevant text", "document_name": "other.md"},
    ]
    metrics = retrieval_metrics(retrieved, [], ["kept for 30 days"], k=5)
    assert metrics["recall@5"] == 1.0
    assert metrics["mrr"] == 1.0


def test_retrieval_metrics_document_names():
    retrieved = [{"content": "anything", "document_name": "Aurora Benchmark Report 2024"}]
    metrics = retrieval_metrics(retrieved, ["Aurora Benchmark Report 2024"], [], k=5)
    assert metrics["hit_rate@5"] == 1.0


def test_citation_metrics():
    citations = [
        {"snippet": "kept for 30 days", "document_name": "report.md"},
        {"snippet": "unrelated claim", "document_name": "other.md"},
    ]
    metrics = citation_metrics(citations, ["report.md"], ["kept for 30 days"])
    assert metrics["citation_precision"] == 0.5
    assert metrics["citation_recall"] == 1.0


def test_citation_metrics_empty():
    assert citation_metrics([], ["doc"], [])["citation_precision"] == 0.0


def test_failure_taxonomy():
    # unanswerable + abstained = correct behaviour, no failure
    assert categorize_failure(answerable=False, abstained=True, retrieval_hit=False,
                              answer_f1=0, citation_precision=0, has_citations=False) == ""
    # unanswerable but answered anyway
    assert categorize_failure(answerable=False, abstained=False, retrieval_hit=True,
                              answer_f1=0.5, citation_precision=1, has_citations=True) \
        == "abstention_failure"
    # answerable, nothing relevant retrieved
    assert categorize_failure(answerable=True, abstained=False, retrieval_hit=False,
                              answer_f1=0.1, citation_precision=0, has_citations=False) \
        == "retrieval_failure"
    # good retrieval, bad answer
    assert categorize_failure(answerable=True, abstained=False, retrieval_hit=True,
                              answer_f1=0.05, citation_precision=1, has_citations=True) \
        == "generation_failure"
    # good answer, bogus citations
    assert categorize_failure(answerable=True, abstained=False, retrieval_hit=True,
                              answer_f1=0.9, citation_precision=0.2, has_citations=True) \
        == "citation_failure"
    # everything fine
    assert categorize_failure(answerable=True, abstained=False, retrieval_hit=True,
                              answer_f1=0.9, citation_precision=1.0, has_citations=True) == ""
