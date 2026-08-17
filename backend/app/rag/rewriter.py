"""Query rewriting: expansion (variants), decomposition, HyDE passages.
LLM calls are cached; every helper degrades to a no-op if the LLM fails —
rewriting must never break retrieval."""

from __future__ import annotations

from app.core.cache import cache
from app.core.logging import get_logger
from app.llm.base import ChatMessage, GenerationParams, LLMProvider
from app.observability.tracing import TraceRecorder
from app.rag import prompts

logger = get_logger("rewriter")


def _track(trace: TraceRecorder | None, llm: LLMProvider, result: dict) -> None:
    if trace is not None and "_usage" in result:
        trace.add_llm_usage(
            llm.name, llm.model, result["_usage"]["prompt"], result["_usage"]["completion"]
        )


async def expand_query(
    llm: LLMProvider, query: str, count: int, trace: TraceRecorder | None = None
) -> list[str]:
    """Generate semantic variants of the query (multi-query retrieval)."""
    cached = await cache.get_rewrite("expand", llm.model, f"{count}:{query}")
    if cached is not None:
        return cached
    try:
        result = await llm.structured_output(
            [
                ChatMessage(role="system", content=prompts.QUERY_REWRITER_SYSTEM),
                ChatMessage(
                    role="user", content=prompts.QUERY_REWRITER_USER.format(count=count, query=query)
                ),
            ],
            schema_hint=prompts.QUERY_REWRITER_SCHEMA,
            params=GenerationParams(temperature=0.4, max_tokens=300),
        )
        _track(trace, llm, result)
        variants = [q.strip() for q in result.get("queries", []) if isinstance(q, str) and q.strip()]
        variants = variants[:count]
        await cache.set_rewrite("expand", llm.model, f"{count}:{query}", variants)
        return variants
    except Exception as exc:  # noqa: BLE001
        logger.warning("query_expansion_failed", error=str(exc)[:200])
        return []


async def hyde_passage(
    llm: LLMProvider, query: str, trace: TraceRecorder | None = None
) -> str:
    """Hypothetical document embedding (HyDE): draft a passage that would
    answer the query, then retrieve with the passage's embedding."""
    cached = await cache.get_rewrite("hyde", llm.model, query)
    if cached is not None:
        return cached
    try:
        result = await llm.generate(
            [
                ChatMessage(role="system", content=prompts.HYDE_SYSTEM),
                ChatMessage(role="user", content=prompts.HYDE_USER.format(query=query)),
            ],
            GenerationParams(temperature=0.3, max_tokens=220),
        )
        if trace is not None:
            trace.add_llm_usage(
                llm.name, llm.model, result.usage.prompt_tokens, result.usage.completion_tokens
            )
        passage = result.text.strip()
        await cache.set_rewrite("hyde", llm.model, query, passage)
        return passage
    except Exception as exc:  # noqa: BLE001
        logger.warning("hyde_failed", error=str(exc)[:200])
        return ""
