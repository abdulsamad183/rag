from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Chunk, Document, DocumentVersion


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")
    return document


async def list_documents(session: AsyncSession, collection_id: uuid.UUID) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.collection_id == collection_id)
        .order_by(Document.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def find_by_hash(
    session: AsyncSession, collection_id: uuid.UUID, content_hash: str
) -> Document | None:
    stmt = select(Document).where(
        Document.collection_id == collection_id, Document.content_hash == content_hash
    )
    return (await session.execute(stmt)).scalars().first()


async def find_by_filename(
    session: AsyncSession, collection_id: uuid.UUID, filename: str
) -> Document | None:
    stmt = select(Document).where(
        Document.collection_id == collection_id, Document.filename == filename
    )
    return (await session.execute(stmt)).scalars().first()


async def delete_document_chunks(
    session: AsyncSession, document_id: uuid.UUID, keep_version: int | None = None
) -> None:
    stmt = delete(Chunk).where(Chunk.document_id == document_id)
    if keep_version is not None:
        stmt = stmt.where(Chunk.doc_version != keep_version)
    await session.execute(stmt)


async def add_version(
    session: AsyncSession, document: Document, storage_path: str, size: int, content_hash: str
) -> DocumentVersion:
    version = DocumentVersion(
        document_id=document.id,
        version=document.current_version,
        content_hash=content_hash,
        storage_path=storage_path,
        size_bytes=size,
    )
    session.add(version)
    return version


async def list_versions(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentVersion]:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
