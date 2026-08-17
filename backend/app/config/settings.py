"""Centralized typed configuration.

Every runtime knob lives here. Application code must never call
``os.getenv`` directly — import :func:`get_settings` instead.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = (".env", "../.env")  # backend/.env wins over repo-root .env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_name: str = "Adaptive Evidence-Driven RAG Engine"
    environment: str = "development"
    secret_key: str = "change-me"
    log_level: str = "INFO"
    json_logs: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- providers ---
    openai_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ollama_base_url: str = "http://localhost:11434"

    default_llm_provider: str = "openai"
    default_llm_model: str = ""  # empty -> provider default
    openai_default_model: str = "gpt-4o-mini"
    groq_default_model: str = "llama-3.1-8b-instant"
    gemini_default_model: str = "gemini-2.0-flash"
    ollama_default_model: str = "llama3.2"

    # --- embeddings ---
    default_embedding_provider: str = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_embedding_model: str = "text-embedding-004"
    ollama_embedding_model: str = "nomic-embed-text"
    embedding_batch_size: int = 64

    # --- reranking ---
    reranker: str = "lexical"  # none | lexical | llm
    rerank_top_k: int = 8

    # --- retrieval ---
    retrieval_strategy: str = "hybrid"
    top_k: int = 10
    candidate_pool_size: int = 30
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3
    rrf_k: int = 60
    max_hops: int = 3
    max_correction_rounds: int = 2
    multi_query_count: int = 3

    # --- chunking ---
    chunking_strategy: str = "recursive"
    chunk_size: int = 800
    chunk_overlap: int = 120
    parent_chunk_size: int = 2400

    # --- generation ---
    temperature: float = 0.1
    max_tokens: int = 1024
    max_context_tokens: int = 6000

    # --- confidence ---
    confidence_high: float = 0.75
    confidence_medium: float = 0.55
    confidence_low: float = 0.35
    abstain_threshold: float = 0.35

    # --- infrastructure ---
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"
    inline_jobs: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # --- storage ---
    storage_backend: str = "local"
    storage_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 50

    # --- resilience ---
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 1.0

    # --- rate limits (requests/minute, 0 disables) ---
    rate_limit_default: int = 120
    rate_limit_chat: int = 30
    rate_limit_uploads: int = 20
    rate_limit_evaluations: int = 6

    # --- caching (seconds) ---
    cache_embeddings_ttl: int = 7 * 24 * 3600
    cache_rewrites_ttl: int = 24 * 3600
    cache_retrieval_ttl: int = 300

    # --- privacy / web ---
    local_mode: bool = False
    web_search_provider: str = "none"

    # --- testing / offline demo ---
    mock_provider: bool = False  # registers the deterministic "mock" LLM + embeddings

    # --- evaluation ---
    eval_judge_provider: str = ""  # empty -> use chat provider
    eval_judge_model: str = ""
    eval_concurrency: int = 2

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> object:
        if isinstance(v, str) and v and not v.startswith("["):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def sync_database_url(self) -> str:
        """URL usable by synchronous drivers (Alembic offline mode)."""
        return self.database_url.replace("+asyncpg", "+psycopg").replace("+aiopg", "")

    def provider_default_model(self, provider: str) -> str:
        return {
            "openai": self.openai_default_model,
            "groq": self.groq_default_model,
            "gemini": self.gemini_default_model,
            "ollama": self.ollama_default_model,
            "mock": "mock-small",
        }.get(provider, "")

    def provider_configured(self, provider: str) -> bool:
        # mock runs fully offline, so it is allowed even in local (privacy) mode
        if provider == "mock":
            return self.mock_provider
        if self.local_mode and provider != "ollama":
            return False
        return {
            "openai": bool(self.openai_api_key),
            "groq": bool(self.groq_api_key),
            "gemini": bool(self.gemini_api_key),
            "ollama": bool(self.ollama_base_url),
        }.get(provider, False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
