"""Job dispatch.

Production: arq worker consuming from Redis (``uv run arq app.workers.worker.WorkerSettings``).
Development/tests: ``INLINE_JOBS=true`` (or unreachable Redis) runs jobs as
fire-and-forget asyncio tasks in-process, so ingestion still never blocks the
HTTP request.

Every job gets a Job row for tracking regardless of transport.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.config import get_settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models import Job
from app.models.base import utcnow

logger = get_logger("queue")

_inline_tasks: set[asyncio.Task] = set()


async def _create_job_row(job_type: str, payload: dict[str, Any]) -> uuid.UUID:
    async with session_scope() as session:
        job = Job(type=job_type, status="queued", payload=payload)
        session.add(job)
        await session.commit()
        return job.id


async def mark_job(job_id: uuid.UUID, status: str, error: str = "", result: dict | None = None) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        if status == "running":
            job.started_at = utcnow()
            job.attempts += 1
        if status in ("completed", "failed"):
            job.finished_at = utcnow()
        if error:
            job.error = error[:2000]
        if result:
            job.result = result
        await session.commit()


async def _run_inline(job_id: uuid.UUID, job_type: str, payload: dict[str, Any]) -> None:
    from app.workers.worker import TASK_MAP

    await mark_job(job_id, "running")
    try:
        await TASK_MAP[job_type](None, **payload)
        await mark_job(job_id, "completed")
    except Exception as exc:  # noqa: BLE001
        logger.error("inline_job_failed", job_type=job_type, error=str(exc)[:300])
        await mark_job(job_id, "failed", error=str(exc))


async def enqueue(job_type: str, **payload: Any) -> uuid.UUID:
    """Dispatch a job; returns the tracking Job id."""
    job_id = await _create_job_row(job_type, payload)
    settings = get_settings()

    if not settings.inline_jobs:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await pool.enqueue_job(job_type, job_id=str(job_id), **payload)
            await pool.aclose()
            logger.info("job_enqueued", job_type=job_type, job_id=str(job_id), transport="arq")
            return job_id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "arq_unavailable_running_inline", job_type=job_type, error=str(exc)[:200]
            )

    task = asyncio.create_task(_run_inline(job_id, job_type, payload))
    _inline_tasks.add(task)
    task.add_done_callback(_inline_tasks.discard)
    logger.info("job_enqueued", job_type=job_type, job_id=str(job_id), transport="inline")
    return job_id
