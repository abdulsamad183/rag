from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.chat import CitationOut


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    collection_ids: list[str]
    summary: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    trace_id: uuid.UUID | None
    meta: dict[str, Any]
    created_at: datetime
    citations: list[CitationOut] = []

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
