"""Fixed-window rate limiting backed by Redis (or the in-memory fallback)."""

from __future__ import annotations

import time

from fastapi import Request

from app.config import get_settings
from app.core.errors import RateLimitedError
from app.core.redis import get_redis


async def _check(identity: str, group: str, limit_per_minute: int) -> None:
    if limit_per_minute <= 0:
        return
    window = int(time.time() // 60)
    key = f"rl:{group}:{identity}:{window}"
    client = await get_redis()
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, 90)
    if count > limit_per_minute:
        raise RateLimitedError(
            f"Rate limit exceeded for {group} ({limit_per_minute}/min). Try again shortly.",
            details={"group": group, "limit_per_minute": limit_per_minute},
        )


def _identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limiter(group: str):
    """Dependency factory: ``Depends(rate_limiter("chat"))``."""

    async def dependency(request: Request) -> None:
        settings = get_settings()
        limit = {
            "default": settings.rate_limit_default,
            "chat": settings.rate_limit_chat,
            "uploads": settings.rate_limit_uploads,
            "evaluations": settings.rate_limit_evaluations,
        }.get(group, settings.rate_limit_default)
        await _check(_identity(request), group, limit)

    return dependency
