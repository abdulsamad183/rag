from __future__ import annotations

import uuid

from app.repositories import chunks as chunk_repo
from app.repositories import graph as graph_repo
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import deduplicate, reciprocal_rank_fusion
from app.retrieval.hybrid import HybridRetrieval
from app.utils.text import content_words, extract_acronyms


class GraphRetrieval(RetrievalStrategy):
    """Entity-centric retrieval over the knowledge graph.

    query entities → matched graph nodes → 1-hop neighbor expansion →
    chunks that mention those entities (scored by mention density) →
    merged with hybrid retrieval as a safety net.
    """

    name = "graph"

    def __init__(self, inner: RetrievalStrategy | None = None):
        self.inner = inner or HybridRetrieval()

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        terms = [e for e in query.analysis.get("entities", []) if isinstance(e, str)]
        if not terms:
            terms = extract_acronyms(query.text) + [
                w for w in content_words(query.text) if len(w) > 3
            ]

        notes: list[str] = []
        with context.trace.step("retrieve.graph", probe_terms=terms[:10]) as step:
            entities = await graph_repo.find_entities_matching(
                context.session, context.collection_ids, terms[:10]
            )
            entity_ids: list[uuid.UUID] = [e.id for e in entities]
            step.payload["matched_entities"] = [
                {"name": e.name, "type": e.type} for e in entities
            ]

            graph_chunks = []
            if entity_ids:
                relations = await graph_repo.expand_neighbors(context.session, entity_ids)
                neighbor_ids = {r.source_id for r in relations} | {r.target_id for r in relations}
                all_ids = list(set(entity_ids) | neighbor_ids)
                step.payload["expanded_entities"] = len(all_ids)
                step.payload["relations"] = [
                    {"relation": r.relation, "weight": r.weight} for r in relations[:15]
                ]

                mention_counts = await graph_repo.chunks_mentioning(context.session, all_ids)
                if mention_counts:
                    fetched = await chunk_repo.get_chunks_by_ids(
                        context.session, list(mention_counts.keys())
                    )
                    max_count = max(mention_counts.values()) or 1
                    for chunk in fetched:
                        density = mention_counts.get(chunk.chunk_id, 0) / max_count
                        # direct entity matches (not just neighbors) score higher
                        chunk.scores["graph"] = density
                        chunk.score = density
                    graph_chunks = fetched
                notes.append(f"{len(entities)} entities matched, {len(graph_chunks)} graph chunks")
            else:
                notes.append("no graph entities matched; falling back to hybrid only")

        baseline = await self.inner.retrieve(query, context)
        fused = deduplicate(reciprocal_rank_fusion([graph_chunks, baseline.chunks]))
        return RetrievalResult(
            chunks=fused[: context.pool_size],
            strategy=self.name,
            queries_used=[query.text],
            notes=notes,
        )
