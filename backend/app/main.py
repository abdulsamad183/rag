"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api.v1 import api_router
from app.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_redis
from app.llm.registry import PROVIDERS

logger = get_logger("main")

OPENAPI_DESCRIPTION = """
**Adaptive Evidence-Driven RAG Engine** — retrieval and reasoning platform.

Pipeline: query understanding → strategy routing → retrieval (vector /
keyword / hybrid / multi-query / multi-hop / graph / temporal) → reranking →
evidence building → grounded generation → claim verification → confidence →
citations (or explicit abstention).
"""


async def validate_startup() -> None:
    """Explicit startup validation (#95): DB is mandatory; everything else is
    reported loudly but does not block boot."""
    settings = get_settings()

    engine = get_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("database_ok")
    except Exception as exc:
        logger.error("database_unreachable", error=str(exc)[:300],
                     url_host=settings.database_url.split("@")[-1])
        raise RuntimeError(
            "Database is unreachable. Start PostgreSQL (docker compose up postgres) "
            "and check DATABASE_URL."
        ) from exc

    await get_redis()  # logs redis vs in-memory fallback

    configured = [p for p in PROVIDERS if settings.provider_configured(p)]
    if configured:
        logger.info("providers_configured", providers=configured)
    else:
        logger.warning(
            "no_providers_configured",
            hint="Set OPENAI_API_KEY / GROQ_API_KEY / GEMINI_API_KEY or run Ollama",
        )

    if settings.storage_backend == "local":
        settings.storage_dir.mkdir(parents=True, exist_ok=True)

    if settings.local_mode:
        logger.info("local_mode_enabled", note="only Ollama allowed; web tools disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    logger.info("starting", app=settings.app_name, version=__version__, env=settings.environment)
    await validate_startup()
    yield
    await dispose_engine()
    logger.info("stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=OPENAPI_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
