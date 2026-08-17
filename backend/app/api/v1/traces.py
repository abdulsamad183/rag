from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DbSession
from app.repositories import traces as trace_repo
from app.schemas.traces import TraceOut, TraceSummary

router = APIRouter(prefix="/retrieval", tags=["observability"])


@router.get("/traces", response_model=list[TraceSummary])
async def list_traces(
    session: DbSession, limit: int = 50, offset: int = 0
) -> list[TraceSummary]:
    traces = await trace_repo.list_traces(session, limit=min(limit, 200), offset=offset)
    return [TraceSummary.model_validate(t) for t in traces]


@router.get("/{trace_id}", response_model=TraceOut)
async def get_trace(trace_id: uuid.UUID, session: DbSession) -> TraceOut:
    return TraceOut.model_validate(await trace_repo.get_trace(session, trace_id))
