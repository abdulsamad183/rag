"""Embedding abstraction, separate from generation providers because
embedding and generation capabilities don't overlap 1:1 across vendors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimension: int
    prompt_tokens: int = 0


@dataclass
class EmbeddingBatchStats:
    texts: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    latency_ms: int = 0

    def merge(self, other: EmbeddingBatchStats) -> None:
        self.texts += other.texts
        self.cache_hits += other.cache_hits
        self.prompt_tokens += other.prompt_tokens
        self.latency_ms += other.latency_ms


@dataclass
class EmbeddingProviderInfo:
    provider: str
    model: str
    dimension: int
    stats: EmbeddingBatchStats = field(default_factory=EmbeddingBatchStats)


class EmbeddingProvider(ABC):
    name: str = ""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a batch of texts. Implementations must preserve order."""

    async def embed_one(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result.vectors[0]
