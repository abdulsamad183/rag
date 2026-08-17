"""Service-level ingestion behaviour: versioning, dedup, embeddings, deletes."""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.db import session_scope
from app.models import Chunk, Collection, Document
from app.repositories.users import get_or_create_default_user
from app.services.documents import upload_document
from app.services.documents import delete_document as remove_document
from app.services.ingestion import ingest_document

DOC_V1 = "# Policy\n\nSnapshots are kept for 30 days.\n\nWAL is kept 7 days.\n"
DOC_V2 = "# Policy\n\nSnapshots are kept for 90 days.\n\nWAL is kept 14 days.\n"


@pytest.fixture()
async def collection(database):
    async with session_scope() as session:
        user = await get_or_create_default_user(session)
        target = Collection(
            user_id=user.id,
            name=f"svc-{uuid.uuid4().hex[:8]}",
            embedding_provider="mock",
            embedding_model="mock-embed",
            chunking_config={"strategy": "markdown", "chunk_size": 400, "chunk_overlap": 60},
        )
        session.add(target)
        await session.commit()
        await session.refresh(target)
        return target


async def test_ingest_produces_embedded_chunks(collection):
    async with session_scope() as session:
        target = await session.get(Collection, collection.id)
        document, is_new = await upload_document(session, target, "policy.md", DOC_V1.encode())
        assert is_new
        await ingest_document(session, document.id)

        await session.refresh(document)
        assert document.status == "completed"
        assert document.chunk_count > 0

        chunks = (
            (await session.execute(select(Chunk).where(Chunk.document_id == document.id)))
            .scalars().all()
        )
        assert chunks
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 64  # mock embedding dimension
            assert chunk.content_hash

        # collection embedding dimension locked in after first ingest
        await session.refresh(target)
        assert target.embedding_dimension == 64


async def test_same_content_is_deduplicated(collection):
    async with session_scope() as session:
        target = await session.get(Collection, collection.id)
        _, first = await upload_document(session, target, "a.md", DOC_V1.encode())
        _, second = await upload_document(session, target, "a.md", DOC_V1.encode())
        assert first is True
        assert second is False


async def test_changed_content_creates_version(collection):
    async with session_scope() as session:
        target = await session.get(Collection, collection.id)
        document, _ = await upload_document(session, target, "policy.md", DOC_V1.encode())
        await ingest_document(session, document.id)

        updated, is_new = await upload_document(session, target, "policy.md", DOC_V2.encode())
        assert is_new
        assert updated.id == document.id  # same logical document
        assert updated.current_version >= 2


async def test_delete_document_removes_chunks(collection):
    async with session_scope() as session:
        target = await session.get(Collection, collection.id)
        document, _ = await upload_document(session, target, "temp.md", DOC_V1.encode())
        await ingest_document(session, document.id)

        await remove_document(session, document.id)

        remaining = (
            await session.execute(
                select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
            )
        ).scalar()
        assert remaining == 0
        assert await session.get(Document, document.id) is None
