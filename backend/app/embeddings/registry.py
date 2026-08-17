from __future__ import annotations

import time

import httpx

from app.config import get_settings
from app.core.cache import cache
from app.core.errors import ProviderNotConfiguredError
from app.embeddings.base import EmbeddingBatchStats, EmbeddingProvider, EmbeddingResult
from app.embeddings.gemini import GeminiEmbeddings
from app.embeddings.mock import MockEmbeddings
from app.embeddings.ollama import OllamaEmbeddings
from app.embeddings.openai import OpenAIEmbeddings

EMBEDDING_PROVIDERS = ("openai", "gemini", "ollama", "mock")


class CachingEmbedder:
    """Wraps a provider with a Redis-backed vector cache and batching."""

    def __init__(self, inner: EmbeddingProvider):
        self.inner = inner
        self.provider = inner.name
        self.model = inner.model

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbeddingBatchStats]:
        started = time.perf_counter()
        stats = EmbeddingBatchStats(texts=len(texts))
        vectors: list[list[float] | None] = [None] * len(texts)
        missing: list[int] = []

        for index, text in enumerate(texts):
            cached = await cache.get_embedding(self.provider, self.model, text)
            if cached is not None:
                vectors[index] = cached
                stats.cache_hits += 1
            else:
                missing.append(index)

        batch_size = get_settings().embedding_batch_size
        for start in range(0, len(missing), batch_size):
            batch_indices = missing[start : start + batch_size]
            batch_texts = [texts[i] for i in batch_indices]
            result: EmbeddingResult = await self.inner.embed(batch_texts)
            stats.prompt_tokens += result.prompt_tokens
            for local, global_index in enumerate(batch_indices):
                vector = result.vectors[local]
                vectors[global_index] = vector
                await cache.set_embedding(self.provider, self.model, texts[global_index], vector)

        stats.latency_ms = int((time.perf_counter() - started) * 1000)
        return [v for v in vectors if v is not None], stats

    async def embed_one(self, text: str) -> list[float]:
        result, _ = await self.embed([text])
        return result[0]


def default_embedding_model(provider: str) -> str:
    settings = get_settings()
    return {
        "openai": settings.openai_embedding_model,
        "gemini": settings.gemini_embedding_model,
        "ollama": settings.ollama_embedding_model,
        "mock": "mock-embed",
    }.get(provider, "")


def get_embedder(
    provider: str | None = None,
    model: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CachingEmbedder:
    settings = get_settings()
    resolved = (provider or settings.default_embedding_provider).lower()
    if settings.local_mode and resolved not in ("ollama", "mock"):
        resolved = "ollama"
    if resolved not in EMBEDDING_PROVIDERS:
        raise ProviderNotConfiguredError(f"Unknown embedding provider '{resolved}'")
    if not settings.provider_configured(resolved):
        raise ProviderNotConfiguredError(
            f"Embedding provider '{resolved}' is not configured (missing API key or base URL)"
        )
    resolved_model = model or default_embedding_model(resolved)
    factories = {
        "openai": OpenAIEmbeddings,
        "gemini": GeminiEmbeddings,
        "ollama": OllamaEmbeddings,
        "mock": MockEmbeddings,
    }
    return CachingEmbedder(factories[resolved](resolved_model, transport=transport))
