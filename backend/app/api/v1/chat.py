from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.rate_limit import rate_limiter
from app.rag.pipeline import PipelineResult
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import build_pipeline_params, execute_chat, prepare_conversation

logger = get_logger("api.chat")

router = APIRouter(prefix="/chat", tags=["chat"])


def _to_response(
    result: PipelineResult,
    request: ChatRequest,
    conversation_id,
    message_id,
    trace_id,
    *,
    include_steps: bool = False,
) -> ChatResponse:
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        trace_id=trace_id,
        answer=result.answer,
        abstained=result.abstained,
        strategy=result.strategy,
        mode=request.mode,
        provider=result.provider,
        model=result.model,
        confidence=result.confidence.as_dict(),
        citations=result.citations,
        evidence=[e.as_dict() for e in result.evidence],
        verification=result.verification.as_dict() if result.verification else None,
        queries_used=result.queries_used,
        correction_rounds=result.correction_rounds,
        fallback_used=result.fallback_used,
        usage=result.trace.usage,
        latency_ms=result.trace.elapsed_ms,
        debug_steps=result.trace.steps_as_dicts() if (request.debug or include_steps) else None,
    )


@router.post("", response_model=ChatResponse, dependencies=[Depends(rate_limiter("chat"))])
async def chat(request: ChatRequest, session: DbSession, user: CurrentUser) -> ChatResponse:
    conversation = await prepare_conversation(
        session, user, request.conversation_id, request.collection_ids, request.message
    )
    params = build_pipeline_params(request.model_dump())
    result, assistant_message, trace_row = await execute_chat(
        session, user, conversation, request.message, request.mode, params
    )
    return _to_response(result, request, conversation.id, assistant_message.id, trace_row.id)


@router.post("/stream", dependencies=[Depends(rate_limiter("chat"))])
async def chat_stream(request: ChatRequest, session: DbSession, user: CurrentUser) -> StreamingResponse:
    """Server-Sent Events stream.

    Events: ``status`` (pipeline stage), ``step`` (completed trace step),
    ``meta`` (ids), ``token`` (answer delta), ``final`` (full verified payload
    — the authoritative answer, which may differ from streamed draft if
    self-correction ran), ``error``.
    """
    queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()

    async def on_token(text: str) -> None:
        await queue.put(("token", {"text": text}))

    async def on_status(stage: str) -> None:
        await queue.put(("status", {"stage": stage}))

    def on_step(step: dict[str, Any]) -> None:
        queue.put_nowait(("step", step))

    async def run() -> None:
        try:
            conversation = await prepare_conversation(
                session, user, request.conversation_id, request.collection_ids, request.message
            )
            await queue.put(("meta", {"conversation_id": str(conversation.id)}))
            params = build_pipeline_params(request.model_dump())
            result, assistant_message, trace_row = await execute_chat(
                session, user, conversation, request.message, request.mode, params,
                on_token=on_token, on_status=on_status, on_step=on_step,
            )
            response = _to_response(
                result, request, conversation.id, assistant_message.id, trace_row.id,
                include_steps=True,
            )
            await queue.put(("final", json.loads(response.model_dump_json())))
        except AppError as exc:
            await queue.put(("error", {"code": exc.code, "message": exc.message}))
        except Exception:  # noqa: BLE001
            logger.exception("chat_stream_failed")
            await queue.put(("error", {"code": "internal_error", "message": "Chat failed unexpectedly."}))
        finally:
            await queue.put(None)

    async def event_source():
        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
