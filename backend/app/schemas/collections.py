from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.chunking import STRATEGIES as CHUNKING_STRATEGIES


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    embedding_provider: str | None = Field(
        default=None, description="openai | gemini | ollama (default: configured provider)"
    )
    embedding_model: str | None = None
    chunking_strategy: str = Field(default="recursive")
    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=120, ge=0, le=2000)
    graph_enabled: bool = False
    temporal_enabled: bool = False
    retrieval_config: dict[str, Any] = Field(default_factory=dict)

    def validated_strategy(self) -> str:
        return self.chunking_strategy if self.chunking_strategy in CHUNKING_STRATEGIES else "recursive"


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    graph_enabled: bool | None = None
    temporal_enabled: bool | None = None
    retrieval_config: dict[str, Any] | None = None
    chunking_config: dict[str, Any] | None = None


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    chunking_config: dict[str, Any]
    retrieval_config: dict[str, Any]
    graph_enabled: bool
    temporal_enabled: bool
    version: int
    created_at: datetime
    document_count: int = 0
    chunk_count: int = 0

    model_config = {"from_attributes": True}
