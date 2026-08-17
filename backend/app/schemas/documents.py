from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    filename: str
    title: str
    source_type: str
    size_bytes: int
    status: str
    progress: float
    error: str
    page_count: int
    chunk_count: int
    current_version: int
    content_hash: str
    meta: dict[str, Any]
    published_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None
    trust: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    content_hash: str
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    level: str
    chunk_index: int
    heading: str
    section_path: str
    page_start: int | None
    page_end: int | None
    content: str
    token_count: int
    meta: dict[str, Any]

    model_config = {"from_attributes": True}


class UploadResult(BaseModel):
    document: DocumentOut
    is_new_content: bool
    message: str = ""
