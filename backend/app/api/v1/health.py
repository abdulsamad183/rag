from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import __version__
from app.api.deps import DbSession
from app.services.health import readiness

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: process is up."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready(session: DbSession) -> dict[str, Any]:
    """Readiness: database, redis, provider configuration, storage."""
    return await readiness(session)
