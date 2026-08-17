"""Redis access with a graceful in-memory fallback.

Production uses Redis (cache, rate limiting, job queue). In development or
tests without Redis, an in-process store keeps the app fully functional —
degraded (no cross-process sharing) but never broken.
"""

from __future__ import annotations

import time
from typing import Any

from redis.asyncio import Redis, from_url

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("redis")

_client: Redis | None = None
_checked = False
_available = False


class InMemoryStore:
    """Minimal async-compatible subset of redis used by the app."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}

    def _expired(self, key: str) -> bool:
        value = self._data.get(key)
        if value is None:
            return True
        _, expires = value
        if expires is not None and expires < time.monotonic():
            del self._data[key]
            return True
        return False

    async def get(self, key: str) -> Any:
        if self._expired(key):
            return None
        return self._data[key][0]

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        expires = time.monotonic() + ex if ex else None
        self._data[key] = (value, expires)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        current = 0 if self._expired(key) else int(self._data[key][0])
        expires = self._data[key][1] if key in self._data else None
        current += 1
        self._data[key] = (current, expires)
        return current

    async def expire(self, key: str, seconds: int) -> None:
        if key in self._data:
            self._data[key] = (self._data[key][0], time.monotonic() + seconds)

    async def scan_iter(self, match: str = "*"):  # pragma: no cover - dev helper
        prefix = match.rstrip("*")
        for key in list(self._data):
            if key.startswith(prefix):
                yield key

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self._data.clear()


_memory = InMemoryStore()


async def get_redis() -> Redis | InMemoryStore:
    """Return a Redis client, or the in-memory fallback if unreachable."""
    global _client, _checked, _available
    if not _checked:
        _checked = True
        try:
            _client = from_url(get_settings().redis_url, decode_responses=True)
            await _client.ping()
            _available = True
            logger.info("redis_connected", url=get_settings().redis_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_unavailable_using_memory", error=str(exc))
            _client = None
            _available = False
    return _client if (_available and _client is not None) else _memory


async def redis_healthy() -> bool:
    client = await get_redis()
    if isinstance(client, InMemoryStore):
        return False
    try:
        await client.ping()
        return True
    except Exception:  # noqa: BLE001
        return False


def reset_redis() -> None:
    """Testing hook."""
    global _client, _checked, _available
    _client = None
    _checked = False
    _available = False
