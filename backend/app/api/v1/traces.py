from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.errors import ValidationFailed
from app.repositories import traces as trace_repo
from app.schemas.traces import RetrievalStatsOut, TraceOut, TraceSummary

router = APIRouter(prefix="/retrieval", tags=["observability"])

_ALLOWED_DAYS = {1, 7, 30}


@router.get("/traces", response_model=list[TraceSummary])
async def list_traces(
    session: DbSession, limit: int = 50, offset: int = 0
) -> list[TraceSummary]:
    traces = await trace_repo.list_traces(session, limit=min(limit, 200), offset=offset)
    return [TraceSummary.model_validate(t) for t in traces]


@router.get("/stats", response_model=RetrievalStatsOut)
async def get_retrieval_stats(
    session: DbSession,
    days: int = Query(default=7, description="Lookback window: 1, 7, or 30"),
) -> RetrievalStatsOut:
    if days not in _ALLOWED_DAYS:
        raise ValidationFailed("days must be one of 1, 7, or 30")
    return await trace_repo.retrieval_stats(session, days=days)


@router.get("/{trace_id}", response_model=TraceOut)
async def get_trace(trace_id: uuid.UUID, session: DbSession) -> TraceOut:
    return TraceOut.model_validate(await trace_repo.get_trace(session, trace_id))
