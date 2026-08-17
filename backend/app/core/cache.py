"""Application-level cache with namespaced keys and JSON values.

Namespaces:
  emb:{model}:{hash}         — embedding vectors
  rw:{model}:{hash}          — query rewrites / analyses
  ret:{collection}:{v}:{hash} — retrieval results (versioned; bumping the
                                collection version invalidates all entries)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.config import get_settings
from app.core.redis import get_redis


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


class Cache:
    async def get_json(self, key: str) -> Any | None:
        client = await get_redis()
        raw = await client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        client = await get_redis()
        await client.set(key, json.dumps(value), ex=ttl)

    # --- embeddings ---
    def embedding_key(self, provider: str, model: str, text: str) -> str:
        return f"emb:{provider}:{model}:{_hash(text)}"

    async def get_embedding(self, provider: str, model: str, text: str) -> list[float] | None:
        return await self.get_json(self.embedding_key(provider, model, text))

    async def set_embedding(self, provider: str, model: str, text: str, vector: list[float]) -> None:
        ttl = get_settings().cache_embeddings_ttl
        await self.set_json(self.embedding_key(provider, model, text), vector, ttl)

    # --- rewrites / analyses ---
    async def get_rewrite(self, kind: str, model: str, query: str) -> Any | None:
        return await self.get_json(f"rw:{kind}:{model}:{_hash(query)}")

    async def set_rewrite(self, kind: str, model: str, query: str, value: Any) -> None:
        await self.set_json(f"rw:{kind}:{model}:{_hash(query)}", value, get_settings().cache_rewrites_ttl)

    # --- retrieval (invalidated by collection version bump) ---
    async def get_retrieval(self, collection_key: str, query_key: str) -> Any | None:
        return await self.get_json(f"ret:{collection_key}:{_hash(query_key)}")

    async def set_retrieval(self, collection_key: str, query_key: str, value: Any) -> None:
        await self.set_json(
            f"ret:{collection_key}:{_hash(query_key)}", value, get_settings().cache_retrieval_ttl
        )


cache = Cache()
