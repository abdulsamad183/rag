import uuid

import pytest

from app.observability.tracing import TraceRecorder
from app.rag.evidence import EvidenceBuilder, render_evidence
from app.retrieval.base import RetrievedChunk


def make_chunk(content: str, score: float, name: str = "") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        score=score,
        scores={"vector": score},
        document_name=name or "doc.md",
    )


@pytest.fixture()
def trace():
    return TraceRecorder()


async def test_builder_orders_by_score_and_assigns_markers(trace):
    chunks = [
        make_chunk("low relevance " * 10, 0.2),
        make_chunk("high relevance " * 10, 0.9),
        make_chunk("mid relevance " * 10, 0.5),
    ]
    builder = EvidenceBuilder(max_context_tokens=5000)
    items = await builder.build(chunks, session=None, trace=trace, expand_parents=False)
    assert [i.marker for i in items] == [1, 2, 3]
    assert items[0].score == 0.9
    assert items[0].content.startswith("high")


async def test_builder_drops_near_duplicates(trace):
    text = "aurora keeps snapshots for thirty days in the retention policy " * 5
    chunks = [make_chunk(text, 0.9), make_chunk(text + " extra", 0.8),
              make_chunk("completely different content about latency", 0.7)]
    builder = EvidenceBuilder(max_context_tokens=5000)
    items = await builder.build(chunks, session=None, trace=trace, expand_parents=False)
    assert len(items) == 2


async def test_builder_respects_token_budget(trace):
    chunks = [make_chunk(f"chunk {i} " + "word " * 400, 1.0 - i * 0.1) for i in range(10)]
    builder = EvidenceBuilder(max_context_tokens=300)
    items = await builder.build(chunks, session=None, trace=trace, expand_parents=False)
    assert 1 <= len(items) < 10


async def test_builder_truncates_single_oversized_chunk(trace):
    chunks = [make_chunk("word " * 5000, 0.9)]
    builder = EvidenceBuilder(max_context_tokens=200)
    items = await builder.build(chunks, session=None, trace=trace, expand_parents=False)
    assert len(items) == 1
    assert len(items[0].content) < 2000


def test_render_evidence_format():
    items_input = [
        make_chunk("The retention is 30 days.", 0.9, name="Report 2024"),
    ]
    builder = EvidenceBuilder(max_context_tokens=1000)
    packed = builder._pack(items_input)
    rendered = render_evidence(packed)
    assert '<evidence id=1 document="Report 2024">' in rendered
    assert "The retention is 30 days." in rendered
    assert "</evidence>" in rendered
