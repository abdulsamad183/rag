from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession
from app.repositories import conversations as conversation_repo
from app.schemas.chat import CitationOut
from app.schemas.common import OkResponse
from app.schemas.conversations import ConversationDetail, ConversationOut, MessageOut
from app.services.export import conversation_to_json, conversation_to_markdown, to_json_str

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(session: DbSession, user: CurrentUser) -> list[ConversationOut]:
    conversations = await conversation_repo.list_conversations(session, user.id)
    return [ConversationOut.model_validate(c) for c in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, session: DbSession) -> ConversationDetail:
    conversation = await conversation_repo.get_conversation(session, conversation_id)
    messages = await conversation_repo.get_messages(session, conversation_id)
    citations = await conversation_repo.get_citations_for_messages(
        session, [m.id for m in messages]
    )
    outs = []
    for message in messages:
        out = MessageOut.model_validate(message)
        out.citations = [
            CitationOut(
                marker=c.marker,
                chunk_id=str(c.chunk_id) if c.chunk_id else "",
                document_id=str(c.document_id) if c.document_id else "",
                document_name=c.document_name,
                page=c.page,
                section=c.section,
                snippet=c.snippet,
                source_url=c.source_url,
                source_type="web" if (c.source_url or "").startswith("http") else "",
                relevance_score=c.relevance_score,
            )
            for c in citations.get(str(message.id), [])
        ]
        outs.append(out)
    return ConversationDetail(
        conversation=ConversationOut.model_validate(conversation), messages=outs
    )


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID,
    session: DbSession,
    format: Literal["markdown", "json"] = "markdown",
) -> Response:
    conversation = await conversation_repo.get_conversation(session, conversation_id)
    messages = await conversation_repo.get_messages(session, conversation_id)
    citations = await conversation_repo.get_citations_for_messages(
        session, [m.id for m in messages]
    )
    if format == "json":
        content = to_json_str(conversation_to_json(conversation, messages, citations))
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.json"'},
        )
    content = conversation_to_markdown(conversation, messages, citations)
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.md"'},
    )


@router.delete("/{conversation_id}", response_model=OkResponse)
async def delete_conversation(conversation_id: uuid.UUID, session: DbSession) -> OkResponse:
    conversation = await conversation_repo.get_conversation(session, conversation_id)
    await session.delete(conversation)
    await session.commit()
    return OkResponse()
