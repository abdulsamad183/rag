"""Deterministic evaluation metrics (pure functions, fully unit-tested).

Ground truth in datasets is expressed portably:
  relevant_documents — document filenames/titles
  relevant_chunks    — content probes (substrings that must appear in a chunk)

A retrieved chunk counts as relevant if it matches either form.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def chunk_is_relevant(
    chunk_content: str, chunk_document: str, relevant_documents: list[str], relevant_chunks: list[str]
) -> bool:
    content = _normalize(chunk_content)
    document = _normalize(chunk_document)
    for probe in relevant_chunks:
        if probe and _normalize(probe) in content:
            return True
    for name in relevant_documents:
        normalized = _normalize(name)
        if normalized and (normalized in document or document in normalized):
            return True
    return False


def relevance_flags(
    retrieved: list[dict[str, Any]], relevant_documents: list[str], relevant_chunks: list[str]
) -> list[bool]:
    return [
        chunk_is_relevant(
            r.get("content", r.get("preview", "")),
            r.get("document_name", ""),
            relevant_documents,
            relevant_chunks,
        )
        for r in retrieved
    ]


def precision_at_k(flags: list[bool], k: int) -> float:
    top = flags[:k]
    return sum(top) / len(top) if top else 0.0


def recall_at_k(flags: list[bool], k: int, total_relevant: int) -> float:
    if total_relevant <= 0:
        return 0.0
    return min(1.0, sum(flags[:k]) / total_relevant)


def hit_rate_at_k(flags: list[bool], k: int) -> float:
    return 1.0 if any(flags[:k]) else 0.0


def mrr(flags: list[bool]) -> float:
    for index, flag in enumerate(flags, start=1):
        if flag:
            return 1.0 / index
    return 0.0


def ndcg_at_k(flags: list[bool], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, flag in enumerate(flags[:k], start=1) if flag)
    ideal_hits = min(sum(flags), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def token_f1(prediction: str, reference: str) -> float:
    """SQuAD-style token overlap F1 against ground-truth answer."""
    pred_tokens = _normalize(prediction).split()
    ref_tokens = _normalize(reference).split()
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = Counter(pred_tokens) & Counter(ref_tokens)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def citation_metrics(
    citations: list[dict[str, Any]],
    relevant_documents: list[str],
    relevant_chunks: list[str],
) -> dict[str, float]:
    if not citations:
        return {"citation_precision": 0.0, "citation_recall": 0.0}
    correct = sum(
        1
        for c in citations
        if chunk_is_relevant(
            c.get("snippet", ""), c.get("document_name", ""), relevant_documents, relevant_chunks
        )
    )
    precision = correct / len(citations)
    cited_docs = {_normalize(c.get("document_name", "")) for c in citations}
    relevant_names = [_normalize(d) for d in relevant_documents if d]
    if relevant_names:
        covered = sum(
            1 for name in relevant_names if any(name in cd or cd in name for cd in cited_docs)
        )
        recall = covered / len(relevant_names)
    else:
        recall = precision  # no doc-level ground truth: fall back to precision
    return {"citation_precision": precision, "citation_recall": recall}


def retrieval_metrics(
    retrieved: list[dict[str, Any]],
    relevant_documents: list[str],
    relevant_chunks: list[str],
    k: int = 5,
) -> dict[str, float]:
    flags = relevance_flags(retrieved, relevant_documents, relevant_chunks)
    total_relevant = max(len(relevant_chunks), 1) if relevant_chunks else (
        1 if relevant_documents else 0
    )
    return {
        f"recall@{k}": recall_at_k(flags, k, total_relevant),
        f"precision@{k}": precision_at_k(flags, k),
        f"hit_rate@{k}": hit_rate_at_k(flags, k),
        "mrr": mrr(flags),
        f"ndcg@{k}": ndcg_at_k(flags, k),
    }


def categorize_failure(
    *,
    answerable: bool,
    abstained: bool,
    retrieval_hit: bool,
    answer_f1: float,
    citation_precision: float,
    has_citations: bool,
) -> str:
    """Deterministic failure taxonomy for the failure-analysis UI."""
    if not answerable:
        return "" if abstained else "abstention_failure"
    if abstained:
        return "retrieval_failure" if not retrieval_hit else "abstention_failure"
    if not retrieval_hit:
        return "retrieval_failure"
    if answer_f1 < 0.15:
        return "generation_failure"
    if has_citations and citation_precision < 0.34:
        return "citation_failure"
    if not has_citations:
        return "citation_failure"
    return ""
