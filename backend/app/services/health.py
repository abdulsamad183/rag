from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.redis import redis_healthy
from app.llm.registry import PROVIDERS


async def readiness(session: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, Any] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": str(exc)[:200]}

    checks["redis"] = {"ok": await redis_healthy()}
    if not checks["redis"]["ok"]:
        checks["redis"]["note"] = "using in-memory fallback (dev only)"

    checks["providers"] = {
        provider: {"configured": settings.provider_configured(provider)} for provider in PROVIDERS
    }
    checks["storage"] = {"ok": settings.storage_dir.exists() or settings.storage_backend != "local"}
    checks["local_mode"] = settings.local_mode

    ready = checks["database"]["ok"]
    return {"ready": ready, "checks": checks}
