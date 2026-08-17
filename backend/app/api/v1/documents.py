from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.config import get_settings
from app.core.errors import FileTooLargeError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models import Chunk, ChunkLevel
from app.repositories import collections as collection_repo
from app.repositories import documents as document_repo
from app.schemas.common import OkResponse
from app.schemas.documents import ChunkOut, DocumentOut, DocumentVersionOut, UploadResult
from app.services.documents import delete_document as remove_document
from app.services.documents import upload_document
from app.services.summarize import summarize_document
from app.storage import get_storage
from app.workers.queue import enqueue

router = APIRouter(tags=["documents"])


@router.post(
    "/collections/{collection_id}/documents",
    response_model=UploadResult,
    status_code=201,
    dependencies=[Depends(rate_limiter("uploads"))],
)
async def upload(
    collection_id: uuid.UUID,
    session: DbSession,
    file: UploadFile = File(...),
    meta: str = Form(default=""),
) -> UploadResult:
    collection = await collection_repo.get_collection(session, collection_id)
    settings = get_settings()

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise FileTooLargeError(f"File exceeds the {settings.max_upload_mb} MB limit")

    parsed_meta: dict = {}
    if meta:
        try:
            parsed_meta = json.loads(meta)
        except json.JSONDecodeError as exc:
            raise ValidationFailed("meta must be valid JSON") from exc

    document, is_new = await upload_document(
        session, collection, file.filename or "upload", data, parsed_meta
    )
    if is_new:
        await enqueue("ingest_document", document_id=str(document.id))
        message = "Queued for ingestion"
    else:
        message = "Identical content already indexed; upload skipped"
    return UploadResult(
        document=DocumentOut.model_validate(document), is_new_content=is_new, message=message
    )


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentOut])
async def list_documents(collection_id: uuid.UUID, session: DbSession) -> list[DocumentOut]:
    await collection_repo.get_collection(session, collection_id)
    documents = await document_repo.list_documents(session, collection_id)
    return [DocumentOut.model_validate(d) for d in documents]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, session: DbSession) -> DocumentOut:
    return DocumentOut.model_validate(await document_repo.get_document(session, document_id))


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionOut])
async def get_versions(document_id: uuid.UUID, session: DbSession) -> list[DocumentVersionOut]:
    await document_repo.get_document(session, document_id)
    versions = await document_repo.list_versions(session, document_id)
    return [DocumentVersionOut.model_validate(v) for v in versions]


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
async def get_document_chunks(
    document_id: uuid.UUID, session: DbSession, limit: int = 100, offset: int = 0
) -> list[ChunkOut]:
    await document_repo.get_document(session, document_id)
    stmt = (
        select(Chunk)
        .where(Chunk.document_id == document_id, Chunk.level == ChunkLevel.CHUNK)
        .order_by(Chunk.chunk_index)
        .offset(offset)
        .limit(min(limit, 200))
    )
    chunks = (await session.execute(stmt)).scalars().all()
    return [ChunkOut.model_validate(c) for c in chunks]


@router.get("/documents/{document_id}/raw")
async def download_document(document_id: uuid.UUID, session: DbSession) -> Response:
    document = await document_repo.get_document(session, document_id)
    data = await get_storage().read(document.storage_path)
    media = {"pdf": "application/pdf", "html": "text/html", "json": "application/json"}.get(
        document.source_type, "application/octet-stream"
    )
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.post("/documents/{document_id}/reingest", response_model=OkResponse)
async def reingest(document_id: uuid.UUID, session: DbSession) -> OkResponse:
    document = await document_repo.get_document(session, document_id)
    document.status = "queued"
    document.progress = 0.0
    document.error = ""
    await session.commit()
    await enqueue("ingest_document", document_id=str(document_id))
    return OkResponse()


@router.post("/documents/{document_id}/summarize")
async def summarize(
    document_id: uuid.UUID, session: DbSession, force: bool = False
) -> dict[str, str]:
    summary = await summarize_document(session, document_id, force=force)
    return {"summary": summary}


@router.delete("/documents/{document_id}", response_model=OkResponse)
async def delete_document(document_id: uuid.UUID, session: DbSession) -> OkResponse:
    await remove_document(session, document_id)
    return OkResponse()
