from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import RetrievalTrace
from app.schemas.traces import (
    CollectionStats,
    LatencyStats,
    ProviderStats,
    RetrievalStatsOut,
    TotalsStats,
)


async def get_trace(session: AsyncSession, trace_id: uuid.UUID) -> RetrievalTrace:
    trace = await session.get(RetrievalTrace, trace_id)
    if trace is None:
        raise NotFoundError(f"Trace {trace_id} not found")
    return trace


async def list_traces(
    session: AsyncSession, limit: int = 50, offset: int = 0
) -> list[RetrievalTrace]:
    stmt = (
        select(RetrievalTrace)
        .order_by(RetrievalTrace.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _percentile(sorted_vals: list[int], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = (len(sorted_vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


async def retrieval_stats(session: AsyncSession, days: int = 7) -> RetrievalStatsOut:
    since = _since(days)
    stmt = select(RetrievalTrace).where(RetrievalTrace.created_at >= since)
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return RetrievalStatsOut(days=days, totals=TotalsStats())

    queries = len(rows)
    abstains = sum(1 for r in rows if r.abstained)
    prompt_tokens = sum(int((r.usage or {}).get("prompt_tokens") or 0) for r in rows)
    completion_tokens = sum(int((r.usage or {}).get("completion_tokens") or 0) for r in rows)
    cost = sum(float((r.usage or {}).get("estimated_cost_usd") or 0.0) for r in rows)
    latencies = sorted(int(r.latency_ms or 0) for r in rows)

    totals = TotalsStats(
        queries=queries,
        abstain_rate=abstains / queries if queries else 0.0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=round(cost, 6),
        latency_ms=LatencyStats(
            mean=round(sum(latencies) / queries, 1) if queries else 0.0,
            p50=round(_percentile(latencies, 0.5), 1),
            p95=round(_percentile(latencies, 0.95), 1),
        ),
    )

    by_provider_map: dict[str, list[RetrievalTrace]] = {}
    for row in rows:
        key = row.provider or "unknown"
        by_provider_map.setdefault(key, []).append(row)

    by_provider: list[ProviderStats] = []
    for provider, group in sorted(by_provider_map.items(), key=lambda kv: -len(kv[1])):
        g_lat = sorted(int(r.latency_ms or 0) for r in group)
        g_n = len(group)
        by_provider.append(
            ProviderStats(
                provider=provider,
                queries=g_n,
                estimated_cost_usd=round(
                    sum(float((r.usage or {}).get("estimated_cost_usd") or 0.0) for r in group), 6
                ),
                prompt_tokens=sum(int((r.usage or {}).get("prompt_tokens") or 0) for r in group),
                completion_tokens=sum(
                    int((r.usage or {}).get("completion_tokens") or 0) for r in group
                ),
                latency_ms_p50=round(_percentile(g_lat, 0.5), 1),
                latency_ms_p95=round(_percentile(g_lat, 0.95), 1),
                abstain_rate=(sum(1 for r in group if r.abstained) / g_n) if g_n else 0.0,
            )
        )

    by_collection_map: dict[str, list[RetrievalTrace]] = {}
    for row in rows:
        ids = list(row.collection_ids or [])
        if not ids:
            by_collection_map.setdefault("none", []).append(row)
        else:
            for cid in ids:
                by_collection_map.setdefault(str(cid), []).append(row)

    by_collection: list[CollectionStats] = []
    for cid, group in sorted(by_collection_map.items(), key=lambda kv: -len(kv[1])):
        g_lat = sorted(int(r.latency_ms or 0) for r in group)
        g_n = len(group)
        by_collection.append(
            CollectionStats(
                collection_id=cid,
                queries=g_n,
                estimated_cost_usd=round(
                    sum(float((r.usage or {}).get("estimated_cost_usd") or 0.0) for r in group), 6
                ),
                latency_ms_p50=round(_percentile(g_lat, 0.5), 1),
                latency_ms_p95=round(_percentile(g_lat, 0.95), 1),
                abstain_rate=(sum(1 for r in group if r.abstained) / g_n) if g_n else 0.0,
            )
        )

    return RetrievalStatsOut(
        days=days,
        totals=totals,
        by_provider=by_provider,
        by_collection=by_collection,
    )
