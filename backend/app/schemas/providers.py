from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ModelOut(BaseModel):
    name: str
    label: str
    context_window: int = 128_000
    capabilities: dict[str, bool] = {}
    installed: bool | None = None  # Ollama: actually pulled locally


class ProviderOut(BaseModel):
    name: str
    label: str
    configured: bool
    default_model: str
    models: list[ModelOut]
    embedding_models: list[dict[str, Any]] = []
    is_local: bool = False
    note: str = ""


class AppConfigOut(BaseModel):
    default_provider: str
    default_embedding_provider: str
    local_mode: bool
    retrieval_defaults: dict[str, Any]
    chunking_strategies: list[str]
    retrieval_strategies: list[str]
    rerankers: list[str]
    modes: list[str]
    web_search_enabled: bool
