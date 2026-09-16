"""Unit tests for retrieval stats aggregation helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models import RetrievalTrace
from app.repositories.traces import _percentile, retrieval_stats


def test_percentile_empty_and_single():
    assert _percentile([], 0.5) == 0.0
    assert _percentile([42], 0.95) == 42.0


def test_percentile_interpolates():
    vals = [10, 20, 30, 40, 50]
    assert _percentile(vals, 0.0) == 10.0
    assert _percentile(vals, 1.0) == 50.0
    assert _percentile(vals, 0.5) == 30.0


@pytest.mark.asyncio
async def test_retrieval_stats_empty_window(database):
    factory = get_session_factory()
    async with factory() as session:
        stats = await retrieval_stats(session, days=7)
        assert stats.days == 7
        assert stats.totals.queries == 0
        assert stats.by_provider == []
        assert stats.by_collection == []


@pytest.mark.asyncio
async def test_retrieval_stats_aggregates_seeded_traces(database):
    factory = get_session_factory()
    cid = str(uuid.uuid4())
    now = datetime.now(UTC)

    async with factory() as session:
        session: AsyncSession
        for i, (provider, latency, abstained, cost) in enumerate(
            [
                ("openai", 100, False, 0.01),
                ("openai", 200, True, 0.02),
                ("ollama", 50, False, 0.0),
            ]
        ):
            session.add(
                RetrievalTrace(
                    query=f"q{i}",
                    provider=provider,
                    model="m",
                    strategy="hybrid",
                    mode="balanced",
                    abstained=abstained,
                    latency_ms=latency,
                    usage={
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "estimated_cost_usd": cost,
                    },
                    collection_ids=[cid] if provider != "ollama" else [],
                    created_at=now - timedelta(hours=1),
                )
            )
        await session.commit()

        stats = await retrieval_stats(session, days=7)
        assert stats.totals.queries == 3
        assert abs(stats.totals.abstain_rate - (1 / 3)) < 1e-6
        assert stats.totals.prompt_tokens == 30
        assert stats.totals.completion_tokens == 15
        assert abs(stats.totals.estimated_cost_usd - 0.03) < 1e-6
        assert stats.totals.latency_ms.p50 > 0
        assert stats.totals.latency_ms.p95 >= stats.totals.latency_ms.p50

        providers = {p.provider: p for p in stats.by_provider}
        assert providers["openai"].queries == 2
        assert providers["ollama"].queries == 1

        collections = {c.collection_id: c for c in stats.by_collection}
        assert cid in collections
        assert collections[cid].queries == 2
        assert "none" in collections
        assert collections["none"].queries == 1
