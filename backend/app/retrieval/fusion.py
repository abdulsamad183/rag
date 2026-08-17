"""Deterministic candidate fusion: Reciprocal Rank Fusion and weighted
score fusion. Pure functions — unit-tested without a database."""

from __future__ import annotations

from collections import defaultdict

from app.retrieval.base import RetrievedChunk


def normalize_scores(chunks: list[RetrievedChunk], source: str) -> None:
    """Min-max normalize chunk.scores[source] in place to 0..1."""
    values = [c.scores.get(source, 0.0) for c in chunks]
    if not values:
        return
    low, high = min(values), max(values)
    span = high - low
    for chunk in chunks:
        raw = chunk.scores.get(source, 0.0)
        chunk.scores[source] = 1.0 if span == 0 else (raw - low) / span


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedChunk]], k: int = 60
) -> list[RetrievedChunk]:
    """RRF: score(d) = Σ 1 / (k + rank_i(d)). Robust to incomparable score
    scales across sources."""
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, RetrievedChunk] = {}
    for result_list in result_lists:
        for rank, chunk in enumerate(result_list, start=1):
            key = str(chunk.chunk_id)
            scores[key] += 1.0 / (k + rank)
            if key not in best or chunk.score > best[key].score:
                existing = best.get(key)
                if existing is not None:
                    existing.scores.update(chunk.scores)
                    best[key] = existing
                else:
                    best[key] = chunk
            else:
                best[key].scores.update(chunk.scores)
    fused = []
    for key, chunk in best.items():
        chunk.score = scores[key]
        chunk.scores["rrf"] = scores[key]
        fused.append(chunk)
    fused.sort(key=lambda c: c.score, reverse=True)
    return fused


def weighted_fusion(
    vector_results: list[RetrievedChunk],
    keyword_results: list[RetrievedChunk],
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[RetrievedChunk]:
    """Weighted linear fusion over min-max-normalized per-source scores."""
    normalize_scores(vector_results, "vector")
    normalize_scores(keyword_results, "keyword")

    merged: dict[str, RetrievedChunk] = {}
    for chunk in vector_results:
        merged[str(chunk.chunk_id)] = chunk
    for chunk in keyword_results:
        key = str(chunk.chunk_id)
        if key in merged:
            merged[key].scores.update(chunk.scores)
        else:
            merged[key] = chunk

    total = semantic_weight + keyword_weight or 1.0
    for chunk in merged.values():
        vec = chunk.scores.get("vector", 0.0)
        kw = chunk.scores.get("keyword", 0.0)
        chunk.score = (semantic_weight * vec + keyword_weight * kw) / total
        chunk.scores["fused"] = chunk.score

    result = list(merged.values())
    result.sort(key=lambda c: c.score, reverse=True)
    return result


def deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Drop exact-id and exact-content duplicates, keeping the best score."""
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    result: list[RetrievedChunk] = []
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        key = str(chunk.chunk_id)
        content_key = chunk.meta.get("content_hash") or chunk.content[:200]
        if key in seen_ids or content_key in seen_hashes:
            continue
        seen_ids.add(key)
        seen_hashes.add(content_key)
        result.append(chunk)
    return result
