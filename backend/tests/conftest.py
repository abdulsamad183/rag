"""Test environment.

Everything runs against real components: an embedded PostgreSQL (pgserver,
which ships pgvector) and the deterministic mock LLM/embedding providers.
No network access, no API keys, no Docker required.

The environment is configured at import time — before any ``app.*`` module is
imported — so the lru-cached Settings pick up the test values.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rag-tests-"))

_ENV = {
    "MOCK_PROVIDER": "1",
    "DEFAULT_LLM_PROVIDER": "mock",
    "DEFAULT_EMBEDDING_PROVIDER": "mock",
    "INLINE_JOBS": "1",
    "STORAGE_DIR": str(_TMP / "uploads"),
    # unreachable on purpose: forces the in-memory redis fallback instantly
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "RATE_LIMIT_DEFAULT": "0",
    "RATE_LIMIT_CHAT": "0",
    "RATE_LIMIT_UPLOADS": "0",
    "RATE_LIMIT_EVALUATIONS": "0",
    "LOG_LEVEL": "WARNING",
    "JSON_LOGS": "0",
    "ENVIRONMENT": "test",
    # keep unit tests deterministic regardless of a developer's backend/.env
    "OPENAI_API_KEY": "",
    "GROQ_API_KEY": "",
    "GEMINI_API_KEY": "",
    "LOCAL_MODE": "0",
}
for key, value in _ENV.items():
    os.environ[key] = value

import pgserver  # noqa: E402

_PG = pgserver.get_server(_TMP / "pgdata")
os.environ["DATABASE_URL"] = f"postgresql+asyncpg://postgres@/postgres?host={_TMP / 'pgdata'}"


def _cleanup() -> None:
    try:
        _PG.cleanup()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)


atexit.register(_cleanup)

# app imports must come after the environment is finalized
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import dispose_engine, get_engine  # noqa: E402
from app.models.base import Base  # noqa: E402


@pytest.fixture(scope="session")
async def database() -> None:
    """Create the schema once for the whole test session."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture()
async def client(database):
    """HTTP client against the real ASGI app (startup validation skipped)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def _clean_database(request):
    """Truncate all tables after each test that touched the database."""
    yield
    if "database" not in request.fixturenames:
        return
    engine = get_engine()
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
