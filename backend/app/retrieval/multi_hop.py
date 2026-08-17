from __future__ import annotations

from dataclasses import replace

from app.llm.base import ChatMessage, GenerationParams
from app.rag import prompts
from app.retrieval.base import Query, RetrievalContext, RetrievalResult, RetrievalStrategy
from app.retrieval.fusion import deduplicate, reciprocal_rank_fusion
from app.retrieval.hybrid import HybridRetrieval
from app.utils.text import truncate_tokens


class MultiHopRetrieval(RetrievalStrategy):
    """Iterative retrieval: retrieve → assess sufficiency → generate the next
    query → retrieve again, bounded by ``max_hops``. Between hops the LLM sees
    only compact evidence previews (structured system data, not chain-of-thought).
    """

    name = "multi_hop"
    PREVIEW_TOKENS = 90
    PREVIEW_CHUNKS = 8

    def __init__(self, inner: RetrievalStrategy | None = None):
        self.inner = inner or HybridRetrieval()

    async def retrieve(self, query: Query, context: RetrievalContext) -> RetrievalResult:
        gathered: list[list] = []
        used_queries: list[str] = []
        notes: list[str] = []
        current_query = query.text
        hops = 0

        for hop in range(max(1, context.max_hops)):
            hops = hop + 1
            result = await self.inner.retrieve(replace(query, text=current_query), context)
            gathered.append(result.chunks)
            used_queries.append(current_query)

            if context.llm is None or hop == context.max_hops - 1:
                break

            merged = deduplicate(reciprocal_rank_fusion(gathered))
            preview = "\n".join(
                f"- [{c.document_name}] {truncate_tokens(c.content, self.PREVIEW_TOKENS)}"
                for c in merged[: self.PREVIEW_CHUNKS]
            )
            try:
                decision = await context.llm.structured_output(
                    [
                        ChatMessage(role="system", content=prompts.MULTI_HOP_NEXT_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=prompts.MULTI_HOP_NEXT_USER.format(
                                query=query.text, evidence=preview
                            ),
                        ),
                    ],
                    schema_hint=prompts.MULTI_HOP_NEXT_SCHEMA,
                    params=GenerationParams(temperature=0.0, max_tokens=250),
                )
                if "_usage" in decision:
                    context.trace.add_llm_usage(
                        context.llm.name, context.llm.model,
                        decision["_usage"]["prompt"], decision["_usage"]["completion"],
                    )
            except Exception:  # noqa: BLE001 — sufficiency check is best-effort
                notes.append(f"hop {hops}: sufficiency check failed, stopping")
                break

            context.trace.add_step(
                "multi_hop.assess",
                hop=hops,
                sufficient=bool(decision.get("sufficient")),
                missing=str(decision.get("missing", ""))[:200],
            )
            if decision.get("sufficient") or not decision.get("next_query"):
                notes.append(f"stopped after hop {hops}: evidence judged sufficient")
                break
            next_query = str(decision["next_query"]).strip()
            if not next_query or next_query.lower() in (q.lower() for q in used_queries):
                notes.append(f"stopped after hop {hops}: no new query")
                break
            current_query = next_query

        fused = deduplicate(reciprocal_rank_fusion(gathered))
        return RetrievalResult(
            chunks=fused[: context.pool_size],
            strategy=self.name,
            queries_used=used_queries,
            hops=hops,
            notes=notes,
        )
