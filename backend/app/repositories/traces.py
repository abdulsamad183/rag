from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import RetrievalTrace


async def get_trace(session: AsyncSession, trace_id: uuid.UUID) -> RetrievalTrace:
    trace = await session.get(RetrievalTrace, trace_id)
    if trace is None:
        raise NotFoundError(f"Trace {trace_id} not found")
    return trace


async def list_traces(
    session: AsyncSession, limit: int = 50, offset: int = 0
) -> list[RetrievalTrace]:
    stmt = (
        select(RetrievalTrace)
        .order_by(RetrievalTrace.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
