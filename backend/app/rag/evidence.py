"""Evidence builder: turns ranked candidates into a compact, deduplicated,
citation-ready evidence set within a token budget.

Steps: near-duplicate removal → parent-child context swap → greedy packing by
score within ``max_context_tokens`` → stable [n] markers with full source
metadata preserved for citations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.tracing import TraceRecorder
from app.repositories import chunks as chunk_repo
from app.retrieval.base import RetrievedChunk
from app.utils.text import estimate_tokens, jaccard

NEAR_DUP_THRESHOLD = 0.85


@dataclass
class EvidenceItem:
    marker: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    content: str
    score: float
    source_type: str = ""
    page: int | None = None
    section: str = ""
    trust: float = 0.6
    scores: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    child_chunk_ids: list[str] = field(default_factory=list)  # when parent-swapped

    def as_dict(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "document_name": self.document_name,
            "content": self.content,
            "score": round(self.score, 4),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "source_type": self.source_type,
            "page": self.page,
            "section": self.section,
            "trust": self.trust,
            "url": self.meta.get("url", ""),
        }


def render_evidence(items: list[EvidenceItem]) -> str:
    """Prompt rendering. Evidence is wrapped in tags and explicitly framed as
    untrusted data by the system prompt. Knowledge-base blocks are listed
    before web blocks so the model prefers them when both exist."""
    ordered = sorted(items, key=lambda item: (item.source_type == "web", item.marker))
    parts = []
    for item in ordered:
        origin = "web" if item.source_type == "web" else "kb"
        header = f'<evidence id={item.marker} origin="{origin}" document="{item.document_name}"'
        url = item.meta.get("url", "")
        if url:
            header += f' url="{url}"'
        if item.page:
            header += f" page={item.page}"
        if item.section:
            header += f' section="{item.section[:120]}"'
        header += ">"
        parts.append(f"{header}\n{item.content}\n</evidence>")
    return "\n\n".join(parts)


class EvidenceBuilder:
    def __init__(self, max_context_tokens: int = 6000, min_score: float = 0.0):
        self.max_context_tokens = max_context_tokens
        self.min_score = min_score

    async def build(
        self,
        candidates: list[RetrievedChunk],
        session: AsyncSession,
        trace: TraceRecorder,
        expand_parents: bool = True,
    ) -> list[EvidenceItem]:
        with trace.step("evidence_builder", candidates=len(candidates)) as step:
            kept = self._drop_near_duplicates(candidates)
            step.payload["after_dedup"] = len(kept)

            if expand_parents:
                kept = await self._swap_parents(kept, session)
                step.payload["after_parent_swap"] = len(kept)

            items = self._pack(kept)
            step.payload["selected"] = len(items)
            step.payload["budget_tokens"] = self.max_context_tokens
            step.payload["used_tokens"] = sum(estimate_tokens(i.content) for i in items)
        return items

    def _drop_near_duplicates(self, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        kept: list[RetrievedChunk] = []
        for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
            if candidate.score < self.min_score:
                continue
            if any(jaccard(candidate.content, existing.content) > NEAR_DUP_THRESHOLD for existing in kept):
                continue
            kept.append(candidate)
        return kept

    async def _swap_parents(
        self, candidates: list[RetrievedChunk], session: AsyncSession
    ) -> list[RetrievedChunk]:
        """Parent-child retrieval: children matched, parents provide context.
        Multiple children of the same parent collapse into one parent entry."""
        parent_ids = list({c.parent_id for c in candidates if c.parent_id is not None})
        if not parent_ids:
            return candidates
        parents = await chunk_repo.get_parent_chunks(session, parent_ids)
        result: list[RetrievedChunk] = []
        used_parents: dict[str, RetrievedChunk] = {}
        for candidate in candidates:
            parent = parents.get(str(candidate.parent_id)) if candidate.parent_id else None
            if parent is None:
                result.append(candidate)
                continue
            key = str(parent.chunk_id)
            if key in used_parents:
                existing = used_parents[key]
                existing.score = max(existing.score, candidate.score)
                existing.meta.setdefault("child_chunk_ids", []).append(str(candidate.chunk_id))
                continue
            swapped = parent
            swapped.score = candidate.score
            swapped.scores = dict(candidate.scores)
            swapped.scores["parent_swap"] = 1.0
            swapped.meta["child_chunk_ids"] = [str(candidate.chunk_id)]
            used_parents[key] = swapped
            result.append(swapped)
        return result

    def _pack(self, candidates: list[RetrievedChunk]) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        budget = self.max_context_tokens
        marker = 1
        for candidate in sorted(
            candidates, key=lambda c: (c.source_type == "web", -c.score)
        ):
            cost = estimate_tokens(candidate.content)
            if cost > budget and items:
                continue
            if cost > budget and not items:
                # Always include at least one evidence block, truncated to budget.
                from app.utils.text import truncate_tokens

                candidate.content = truncate_tokens(candidate.content, budget)
                cost = estimate_tokens(candidate.content)
            items.append(
                EvidenceItem(
                    marker=marker,
                    chunk_id=candidate.chunk_id,
                    document_id=candidate.document_id,
                    document_name=candidate.document_name,
                    content=candidate.content,
                    score=candidate.score,
                    source_type=candidate.source_type,
                    page=candidate.page_start,
                    section=candidate.section_path or candidate.heading,
                    trust=candidate.trust,
                    scores=candidate.scores,
                    meta=candidate.meta,
                    child_chunk_ids=candidate.meta.get("child_chunk_ids", []),
                )
            )
            marker += 1
            budget -= cost
            if budget <= 0:
                break
        return items
