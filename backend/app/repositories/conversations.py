from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Citation, Conversation, Message


async def get_conversation(session: AsyncSession, conversation_id: uuid.UUID) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} not found")
    return conversation


async def list_conversations(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 50
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_messages(session: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_citations_for_messages(
    session: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[str, list[Citation]]:
    if not message_ids:
        return {}
    stmt = select(Citation).where(Citation.message_id.in_(message_ids)).order_by(Citation.marker)
    citations = (await session.execute(stmt)).scalars().all()
    grouped: dict[str, list[Citation]] = {}
    for citation in citations:
        grouped.setdefault(str(citation.message_id), []).append(citation)
    return grouped
