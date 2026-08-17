from __future__ import annotations

import math
from collections import Counter

from app.reranking.base import Reranker
from app.retrieval.base import RetrievedChunk
from app.utils.text import content_words


class LexicalReranker(Reranker):
    """Deterministic BM25-style rescoring over the candidate pool.

    No model calls: computes BM25 with corpus statistics limited to the pool,
    blended with the first-stage score. A solid default that keeps the
    pipeline fully functional without any reranking provider.
    """

    name = "lexical"
    K1 = 1.5
    B = 0.75
    BLEND = 0.5  # weight of BM25 vs first-stage score

    async def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        query_terms = content_words(query)
        if not query_terms:
            return chunks[:top_k]

        docs = [content_words(c.content) for c in chunks]
        doc_freqs = [Counter(d) for d in docs]
        avg_len = sum(len(d) for d in docs) / len(docs) or 1.0
        n = len(docs)

        idf: dict[str, float] = {}
        for term in set(query_terms):
            containing = sum(1 for d in doc_freqs if term in d)
            idf[term] = math.log((n - containing + 0.5) / (containing + 0.5) + 1.0)

        bm25_scores: list[float] = []
        for freq, doc in zip(doc_freqs, docs, strict=True):
            score = 0.0
            doc_len = len(doc) or 1
            for term in query_terms:
                tf = freq.get(term, 0)
                if tf == 0:
                    continue
                score += idf[term] * (tf * (self.K1 + 1)) / (
                    tf + self.K1 * (1 - self.B + self.B * doc_len / avg_len)
                )
            bm25_scores.append(score)

        high = max(bm25_scores) or 1.0
        for chunk, raw in zip(chunks, bm25_scores, strict=True):
            normalized = raw / high
            chunk.scores["rerank"] = normalized
            chunk.score = self.BLEND * normalized + (1 - self.BLEND) * chunk.score

        reranked = sorted(chunks, key=lambda c: c.score, reverse=True)
        return reranked[:top_k]
