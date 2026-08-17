"""Retrieval strategies against real pgvector + FTS with mock embeddings."""

import uuid

import pytest

from app.config.profiles import PROFILES
from app.core.db import session_scope
from app.embeddings.registry import get_embedder
from app.models import Collection
from app.observability.tracing import TraceRecorder
from app.repositories.users import get_or_create_default_user
from app.retrieval.base import Query, QueryFilters, RetrievalContext
from app.retrieval.registry import get_strategy as _get_strategy
from app.services.documents import upload_document
from app.services.ingestion import ingest_document


def get_strategy(name: str):
    return _get_strategy(name, PROFILES["balanced"])

DOCS = {
    "latency.md": (
        "# Latency Report\n\nThe median query latency of the Aurora database was "
        "nine milliseconds in the 2025 benchmark run on upgraded hardware.\n"
    ),
    "errors.md": (
        "# Error Reference\n\nError code AUR-1002 indicates a dimension mismatch "
        "between the query vector and the target collection.\n"
    ),
    "cooking.md": (
        "# Pasta Guide\n\nCooking pasta requires generously salted boiling water "
        "and precise timing for al dente texture.\n"
    ),
}


@pytest.fixture()
async def seeded(database):
    async with session_scope() as session:
        user = await get_or_create_default_user(session)
        collection = Collection(
            user_id=user.id,
            name=f"ret-{uuid.uuid4().hex[:8]}",
            embedding_provider="mock",
            embedding_model="mock-embed",
            chunking_config={"strategy": "markdown", "chunk_size": 500, "chunk_overlap": 50},
        )
        session.add(collection)
        await session.commit()
        for filename, content in DOCS.items():
            document, _ = await upload_document(session, collection, filename, content.encode())
            await ingest_document(session, document.id)
        await session.refresh(collection)
        return collection.id


def make_context(session, collection, **overrides) -> RetrievalContext:
    defaults = dict(
        session=session,
        collections=[collection],
        trace=TraceRecorder(),
        top_k=5,
        pool_size=10,
        embedder=get_embedder("mock", "mock-embed"),
    )
    defaults.update(overrides)
    return RetrievalContext(**defaults)


async def test_vector_retrieval_ranks_on_topic_first(seeded):
    async with session_scope() as session:
        collection = await session.get(Collection, seeded)
        context = make_context(session, collection)
        result = await get_strategy("vector").retrieve(
            Query(text="median query latency milliseconds benchmark"), context
        )
        assert result.chunks
        assert "latency" in result.chunks[0].content.lower()
        assert result.chunks[0].scores.get("vector") is not None


async def test_keyword_retrieval_finds_exact_code(seeded):
    async with session_scope() as session:
        collection = await session.get(Collection, seeded)
        context = make_context(session, collection)
        result = await get_strategy("keyword").retrieve(Query(text="AUR-1002"), context)
        assert result.chunks
        assert "AUR-1002" in result.chunks[0].content


async def test_hybrid_combines_sources(seeded):
    async with session_scope() as session:
        collection = await session.get(Collection, seeded)
        context = make_context(session, collection)
        result = await get_strategy("hybrid").retrieve(
            Query(text="dimension mismatch error code"), context
        )
        assert result.chunks
        top = result.chunks[0]
        assert "mismatch" in top.content.lower()
        # hybrid records at least one of the source scores
        assert any(k in top.scores for k in ("vector", "keyword", "rrf", "fused"))


async def test_document_filter_restricts_results(seeded):
    async with session_scope() as session:
        collection = await session.get(Collection, seeded)
        from app.models import Document
        from sqlalchemy import select

        cooking_doc = (
            await session.execute(
                select(Document).where(
                    Document.collection_id == seeded, Document.filename == "cooking.md"
                )
            )
        ).scalars().first()

        context = make_context(session, collection)
        result = await get_strategy("vector").retrieve(
            Query(
                text="anything at all",
                filters=QueryFilters(document_ids=[cooking_doc.id]),
            ),
            context,
        )
        assert result.chunks
        assert all(c.document_id == cooking_doc.id for c in result.chunks)


async def test_multi_query_with_mock_llm(seeded):
    from app.llm.registry import get_llm

    async with session_scope() as session:
        collection = await session.get(Collection, seeded)
        context = make_context(session, collection, llm=get_llm("mock", "mock-small"))
        result = await get_strategy("multi_query").retrieve(
            Query(text="Compare latency and error handling in Aurora"), context
        )
        assert result.chunks
        assert len(result.queries_used) >= 2
