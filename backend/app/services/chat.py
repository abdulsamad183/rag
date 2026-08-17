"""Chat orchestration: conversation handling, pipeline execution, persistence
(messages, citations, trace), rolling summary updates, and streaming."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.config.profiles import get_profile
from app.core.logging import get_logger
from app.embeddings.registry import get_embedder
from app.llm.registry import get_llm
from app.models import Citation, Conversation, Message, RetrievalTrace, User
from app.rag.memory import SHORT_TERM_MESSAGES, update_summary
from app.rag.pipeline import PipelineParams, PipelineResult, RAGPipeline, StreamCallback
from app.repositories import collections as collection_repo
from app.repositories import conversations as conversation_repo

logger = get_logger("chat")


async def prepare_conversation(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID | None,
    collection_ids: list[uuid.UUID],
    first_message: str,
) -> Conversation:
    if conversation_id is not None:
        conversation = await conversation_repo.get_conversation(session, conversation_id)
        conversation.collection_ids = [str(c) for c in collection_ids]
        return conversation
    title = first_message.strip()[:80] or "New conversation"
    conversation = Conversation(
        user_id=user.id, title=title, collection_ids=[str(c) for c in collection_ids]
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def execute_chat(
    session: AsyncSession,
    user: User,
    conversation: Conversation,
    message_text: str,
    mode: str,
    params: PipelineParams,
    on_token: StreamCallback | None = None,
    on_status: StreamCallback | None = None,
) -> tuple[PipelineResult, Message, RetrievalTrace]:
    collection_ids = [uuid.UUID(c) for c in conversation.collection_ids]
    collections = await collection_repo.get_collections(session, collection_ids)
    profile = get_profile(mode)

    history = await conversation_repo.get_messages(session, conversation.id)

    # All selected collections must share one embedding space.
    first = collections[0]
    for other in collections[1:]:
        if (
            other.embedding_provider != first.embedding_provider
            or other.embedding_model != first.embedding_model
        ):
            from app.core.errors import EmbeddingMismatchError

            raise EmbeddingMismatchError(
                "Selected collections use different embedding models and cannot be "
                "searched together. Select collections that share an embedding model."
            )
    embedder = get_embedder(first.embedding_provider, first.embedding_model)

    pipeline = RAGPipeline(
        session=session,
        collections=collections,
        profile=profile,
        params=params,
        embedder=embedder,
    )
    result = await pipeline.run(
        message_text,
        history=history,
        summary=conversation.summary,
        on_token=on_token,
        on_status=on_status,
    )

    user_message = Message(conversation_id=conversation.id, role="user", content=message_text)
    session.add(user_message)

    trace_row = RetrievalTrace(
        request_id=result.trace.request_id,
        user_id=user.id,
        conversation_id=conversation.id,
        query=message_text,
        mode=mode,
        strategy=result.strategy,
        provider=result.provider,
        model=result.model,
        query_analysis=_scrub(result.analysis),
        steps=result.trace.steps_as_dicts(),
        retrieved=result.trace.retrieved,
        verification=result.verification.as_dict() if result.verification else {},
        confidence=result.confidence.as_dict(),
        usage=result.trace.usage,
        answer=result.answer,
        abstained=result.abstained,
        latency_ms=result.trace.elapsed_ms,
    )
    session.add(trace_row)
    await session.flush()

    assistant_meta: dict[str, Any] = {
        "confidence": result.confidence.as_dict(),
        "strategy": result.strategy,
        "mode": mode,
        "provider": result.provider,
        "model": result.model,
        "abstained": result.abstained,
        "usage": result.trace.usage,
        "latency_ms": result.trace.elapsed_ms,
        "correction_rounds": result.correction_rounds,
        "evidence_count": len(result.evidence),
        "fallback_used": result.fallback_used,
    }
    if result.verification is not None:
        assistant_meta["verification"] = {
            "supported": result.verification.supported,
            "total": result.verification.total,
            "contradictions": len(result.verification.contradictions),
        }

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result.answer,
        trace_id=trace_row.id,
        meta=assistant_meta,
    )
    session.add(assistant_message)
    await session.flush()

    for citation in result.citations:
        session.add(
            Citation(
                message_id=assistant_message.id,
                chunk_id=uuid.UUID(citation["chunk_id"]),
                document_id=uuid.UUID(citation["document_id"]),
                marker=citation["marker"],
                document_name=citation["document_name"],
                page=citation.get("page"),
                section=citation.get("section", ""),
                snippet=citation.get("snippet", ""),
                source_url=citation.get("source_url", ""),
                relevance_score=citation.get("relevance_score", 0.0),
            )
        )

    # Rolling summary memory: refresh once the window overflows.
    if len(history) + 2 > SHORT_TERM_MESSAGES and not result.abstained:
        try:
            llm = get_llm(result.provider, result.model)
            conversation.summary = await update_summary(
                llm, conversation.summary, message_text, result.answer
            )
        except Exception:  # noqa: BLE001 — memory upkeep is best-effort
            logger.warning("summary_update_skipped")

    await session.commit()
    return result, assistant_message, trace_row


def _scrub(analysis: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in analysis.items() if not k.startswith("_")}


def build_pipeline_params(payload: dict[str, Any]) -> PipelineParams:
    """Translate API chat options into pipeline parameters."""
    settings = get_settings()
    params = PipelineParams(
        provider=payload.get("provider"),
        model=payload.get("model"),
        temperature=payload.get("temperature"),
        max_tokens=payload.get("max_tokens"),
        max_context_tokens=payload.get("max_context_tokens"),
        top_k=payload.get("top_k"),
        rerank_top_k=payload.get("rerank_top_k"),
        strategy=payload.get("retrieval_strategy"),
        reranker=payload.get("reranker"),
        max_hops=payload.get("max_hops"),
        confidence_threshold=payload.get("confidence_threshold"),
        allow_fallback=bool(payload.get("allow_fallback", False)),
    )
    if settings.local_mode:
        params.provider = "ollama"
    return params
