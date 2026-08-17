from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Collection(Base, TimestampMixin):
    """A user-scoped knowledge base with its own embedding + retrieval config.

    ``embedding_*`` pin the vector space of every chunk in this collection —
    queries are always embedded with the same model, and switching models
    requires reindexing (enforced, not assumed).
    ``version`` increments whenever indexed content changes; caches key on it.
    """

    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_collections_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")

    embedding_provider: Mapped[str] = mapped_column(String(50))
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_dimension: Mapped[int] = mapped_column(default=0)  # 0 until first embed
    embedding_version: Mapped[int] = mapped_column(default=1)

    chunking_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    graph_enabled: Mapped[bool] = mapped_column(default=False)
    temporal_enabled: Mapped[bool] = mapped_column(default=False)

    version: Mapped[int] = mapped_column(default=1)

    def cache_key(self) -> str:
        return f"{self.id}:{self.version}"
