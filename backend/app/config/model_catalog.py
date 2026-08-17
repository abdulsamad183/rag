"""Central model catalog: capabilities, context windows, pricing.

Models are configuration, not code. The catalog below ships sane defaults
and can be extended/overridden with a JSON file pointed to by the
``MODEL_CATALOG_PATH`` environment variable (same shape as ``DEFAULT_CATALOG``).
Adding a model never requires touching pipeline code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class ModelCapabilities:
    streaming: bool = True
    json_output: bool = True
    tools: bool = False
    vision: bool = False


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1M tokens. Zero for local models."""

    input_per_1m: float = 0.0
    output_per_1m: float = 0.0


@dataclass(frozen=True)
class ModelInfo:
    name: str
    label: str
    context_window: int = 128_000
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    pricing: ModelPricing = field(default_factory=ModelPricing)


@dataclass(frozen=True)
class EmbeddingModelInfo:
    name: str
    dimension: int
    pricing: ModelPricing = field(default_factory=ModelPricing)


DEFAULT_CATALOG: dict[str, list[ModelInfo]] = {
    "openai": [
        ModelInfo("gpt-4o-mini", "GPT-4o mini", 128_000,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(0.15, 0.60)),
        ModelInfo("gpt-4o", "GPT-4o", 128_000,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(2.50, 10.00)),
        ModelInfo("gpt-4.1-mini", "GPT-4.1 mini", 1_000_000,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(0.40, 1.60)),
        ModelInfo("gpt-4.1", "GPT-4.1", 1_000_000,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(2.00, 8.00)),
    ],
    "groq": [
        ModelInfo("llama-3.1-8b-instant", "Llama 3.1 8B Instant", 131_072,
                  ModelCapabilities(tools=True), ModelPricing(0.05, 0.08)),
        ModelInfo("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile", 131_072,
                  ModelCapabilities(tools=True), ModelPricing(0.59, 0.79)),
        ModelInfo("openai/gpt-oss-20b", "GPT-OSS 20B", 131_072,
                  ModelCapabilities(tools=True), ModelPricing(0.10, 0.50)),
    ],
    "gemini": [
        ModelInfo("gemini-2.0-flash", "Gemini 2.0 Flash", 1_048_576,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(0.10, 0.40)),
        ModelInfo("gemini-2.0-flash-lite", "Gemini 2.0 Flash Lite", 1_048_576,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(0.075, 0.30)),
        ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", 1_048_576,
                  ModelCapabilities(tools=True, vision=True), ModelPricing(0.30, 2.50)),
    ],
    "ollama": [
        # Local models: whatever is pulled locally also appears dynamically;
        # these are common defaults shown even before the daemon is queried.
        ModelInfo("llama3.2", "Llama 3.2 (local)", 131_072, ModelCapabilities()),
        ModelInfo("llama3.1", "Llama 3.1 (local)", 131_072, ModelCapabilities()),
        ModelInfo("qwen2.5", "Qwen 2.5 (local)", 32_768, ModelCapabilities()),
        ModelInfo("mistral", "Mistral (local)", 32_768, ModelCapabilities()),
    ],
    "mock": [
        ModelInfo("mock-small", "Mock (deterministic, offline)", 32_768, ModelCapabilities()),
    ],
}

DEFAULT_EMBEDDINGS: dict[str, list[EmbeddingModelInfo]] = {
    "openai": [
        EmbeddingModelInfo("text-embedding-3-small", 1536, ModelPricing(0.02, 0.0)),
        EmbeddingModelInfo("text-embedding-3-large", 3072, ModelPricing(0.13, 0.0)),
    ],
    "gemini": [
        EmbeddingModelInfo("text-embedding-004", 768),
        EmbeddingModelInfo("gemini-embedding-001", 3072),
    ],
    "ollama": [
        EmbeddingModelInfo("nomic-embed-text", 768),
        EmbeddingModelInfo("mxbai-embed-large", 1024),
        EmbeddingModelInfo("all-minilm", 384),
    ],
    "mock": [
        EmbeddingModelInfo("mock-embed", 64),
    ],
}


def _load_override() -> dict:
    path = os.environ.get("MODEL_CATALOG_PATH", "")
    if not path:
        return {}
    file = Path(path)
    if not file.exists():
        return {}
    return json.loads(file.read_text())


@lru_cache
def get_catalog() -> dict[str, list[ModelInfo]]:
    catalog = {k: list(v) for k, v in DEFAULT_CATALOG.items()}
    override = _load_override().get("models", {})
    for provider, models in override.items():
        parsed = [
            ModelInfo(
                name=m["name"],
                label=m.get("label", m["name"]),
                context_window=m.get("context_window", 128_000),
                capabilities=ModelCapabilities(**m.get("capabilities", {})),
                pricing=ModelPricing(**m.get("pricing", {})),
            )
            for m in models
        ]
        existing = {x.name for x in catalog.get(provider, [])}
        catalog.setdefault(provider, [])
        catalog[provider] = [x for x in catalog[provider] if x.name in existing] + [
            p for p in parsed if p.name not in existing
        ]
    return catalog


@lru_cache
def get_embedding_catalog() -> dict[str, list[EmbeddingModelInfo]]:
    catalog = {k: list(v) for k, v in DEFAULT_EMBEDDINGS.items()}
    override = _load_override().get("embeddings", {})
    for provider, models in override.items():
        parsed = [
            EmbeddingModelInfo(
                name=m["name"],
                dimension=m["dimension"],
                pricing=ModelPricing(**m.get("pricing", {})),
            )
            for m in models
        ]
        names = {p.name for p in parsed}
        catalog.setdefault(provider, [])
        catalog[provider] = [x for x in catalog[provider] if x.name not in names] + parsed
    return catalog


def find_model(provider: str, model: str) -> ModelInfo | None:
    for info in get_catalog().get(provider, []):
        if info.name == model:
            return info
    return None


def find_embedding_model(provider: str, model: str) -> EmbeddingModelInfo | None:
    for info in get_embedding_catalog().get(provider, []):
        if info.name == model:
            return info
    return None


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    info = find_model(provider, model)
    if info is None:
        return 0.0
    return (
        prompt_tokens * info.pricing.input_per_1m
        + completion_tokens * info.pricing.output_per_1m
    ) / 1_000_000
