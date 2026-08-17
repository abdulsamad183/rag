"""arq worker: background tasks for ingestion, graph extraction, and
evaluation runs.

Run with:  uv run arq app.workers.worker.WorkerSettings
"""

from __future__ import annotations

import uuid
from typing import Any

from arq.connections import RedisSettings

from app.config import get_settings
from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger

logger = get_logger("worker")


async def ingest_document(ctx: dict[str, Any] | None, document_id: str, job_id: str | None = None) -> None:
    from app.repositories import collections as collection_repo
    from app.repositories import documents as document_repo
    from app.services.ingestion import ingest_document as run_ingestion
    from app.workers.queue import enqueue, mark_job

    if job_id:
        await mark_job(uuid.UUID(job_id), "running")
    try:
        async with session_scope() as session:
            await run_ingestion(session, uuid.UUID(document_id))
            document = await document_repo.get_document(session, uuid.UUID(document_id))
            collection = await collection_repo.get_collection(session, document.collection_id)
            graph_enabled = collection.graph_enabled
        if graph_enabled:
            await enqueue("extract_graph", document_id=document_id)
        if job_id:
            await mark_job(uuid.UUID(job_id), "completed")
    except Exception as exc:
        if job_id:
            await mark_job(uuid.UUID(job_id), "failed", error=str(exc))
        raise


async def extract_graph(ctx: dict[str, Any] | None, document_id: str, job_id: str | None = None) -> None:
    from app.services.graph import extract_document_graph
    from app.workers.queue import mark_job

    if job_id:
        await mark_job(uuid.UUID(job_id), "running")
    try:
        async with session_scope() as session:
            result = await extract_document_graph(session, uuid.UUID(document_id))
        if job_id:
            await mark_job(uuid.UUID(job_id), "completed", result=result)
    except Exception as exc:
        if job_id:
            await mark_job(uuid.UUID(job_id), "failed", error=str(exc))
        raise


async def run_evaluation(ctx: dict[str, Any] | None, run_id: str, job_id: str | None = None) -> None:
    from app.services.evaluation import run_evaluation as execute
    from app.workers.queue import mark_job

    if job_id:
        await mark_job(uuid.UUID(job_id), "running")
    try:
        async with session_scope() as session:
            await execute(session, uuid.UUID(run_id))
        if job_id:
            await mark_job(uuid.UUID(job_id), "completed")
    except Exception as exc:
        if job_id:
            await mark_job(uuid.UUID(job_id), "failed", error=str(exc))
        raise


TASK_MAP = {
    "ingest_document": ingest_document,
    "extract_graph": extract_graph,
    "run_evaluation": run_evaluation,
}


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    logger.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    from app.core.db import dispose_engine

    await dispose_engine()
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [ingest_document, extract_graph, run_evaluation]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 1800
    max_tries = 2
