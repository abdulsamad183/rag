"""Deterministic offline embeddings (enabled with MOCK_PROVIDER=1).

Bag-of-words feature hashing into a small dense vector: texts sharing
vocabulary get high cosine similarity, so vector retrieval behaves sensibly
in tests and offline demos. Stable across processes (zlib.crc32, not the
salted builtin ``hash``).
"""

from __future__ import annotations

import math
import re
import zlib
from typing import Any

from app.embeddings.base import EmbeddingProvider, EmbeddingResult

DIMENSION = 64
_WORD = re.compile(r"[a-z0-9]{2,}")


def _vectorize(text: str) -> list[float]:
    vector = [0.0] * DIMENSION
    words = _WORD.findall(text.lower())
    for word in words:
        bucket = zlib.crc32(word.encode()) % DIMENSION
        vector[bucket] += 1.0
        # a second hash reduces bucket collisions dominating similarity
        bucket2 = zlib.crc32(b"salt:" + word.encode()) % DIMENSION
        vector[bucket2] += 0.5
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


class MockEmbeddings(EmbeddingProvider):
    name = "mock"

    def __init__(self, model: str = "mock-embed", transport: Any = None):
        super().__init__(model or "mock-embed")

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors = [_vectorize(t) for t in texts]
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            dimension=DIMENSION,
            prompt_tokens=sum(max(1, len(t) // 4) for t in texts),
        )
