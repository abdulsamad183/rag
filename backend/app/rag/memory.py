"""Conversational memory: short-term window + rolling summary +
retrieval-aware follow-up contextualization.

The full chat history is never dumped into prompts. Retrieval sees a
standalone rewritten query; generation sees a compact conversation context
(summary + last exchange) only when one exists.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger
from app.llm.base import ChatMessage, GenerationParams, LLMProvider
from app.models import Message
from app.observability.tracing import TraceRecorder
from app.rag import prompts

logger = get_logger("memory")

_REFERENTIAL = re.compile(
    r"\b(it|its|they|them|these|those|this|that|he|she|his|her|the same|also|too|as well)\b", re.I
)
SHORT_TERM_MESSAGES = 6


def looks_referential(query: str) -> bool:
    return bool(_REFERENTIAL.search(query)) or len(query.split()) <= 4


async def contextualize_query(
    llm: LLMProvider | None,
    query: str,
    history: list[Message],
    summary: str,
    trace: TraceRecorder,
) -> str:
    """Rewrite a follow-up into a standalone retrieval query when needed."""
    if not history or llm is None:
        return query
    if not looks_referential(query):
        trace.add_step("contextualize", changed=False, reason="query is self-contained")
        return query

    recent = history[-SHORT_TERM_MESSAGES:]
    rendered = "\n".join(f"{m.role}: {m.content[:400]}" for m in recent)
    try:
        result = await llm.structured_output(
            [
                ChatMessage(role="system", content=prompts.CONTEXTUALIZER_SYSTEM),
                ChatMessage(
                    role="user",
                    content=prompts.CONTEXTUALIZER_USER.format(
                        summary=summary or "(none)", history=rendered, query=query
                    ),
                ),
            ],
            schema_hint=prompts.CONTEXTUALIZER_SCHEMA,
            params=GenerationParams(temperature=0.0, max_tokens=200),
        )
        usage = result.pop("_usage", None)
        if usage:
            trace.add_llm_usage(llm.name, llm.model, usage["prompt"], usage["completion"])
        standalone = str(result.get("standalone_query", "")).strip()
        changed = bool(result.get("changed")) and bool(standalone)
        trace.add_step(
            "contextualize", changed=changed,
            rewritten=standalone[:200] if changed else "",
        )
        return standalone if changed else query
    except Exception as exc:  # noqa: BLE001
        logger.warning("contextualize_failed", error=str(exc)[:200])
        return query


def build_generation_context(history: list[Message], summary: str) -> str:
    """Compact conversation context injected before the question."""
    if not history and not summary:
        return ""
    parts = []
    if summary:
        parts.append(f"Conversation summary: {summary}")
    recent = history[-2:]
    if recent:
        rendered = "\n".join(f"{m.role}: {m.content[:300]}" for m in recent)
        parts.append(f"Recent exchange:\n{rendered}")
    return "\n\n".join(parts) + "\n\n"


async def update_summary(
    llm: LLMProvider, old_summary: str, user_message: str, assistant_message: str
) -> str:
    try:
        result = await llm.generate(
            [
                ChatMessage(role="system", content=prompts.SUMMARIZER_SYSTEM),
                ChatMessage(
                    role="user",
                    content=prompts.CONVERSATION_SUMMARY_USER.format(
                        summary=old_summary or "(empty)",
                        user_message=user_message[:800],
                        assistant_message=assistant_message[:800],
                    ),
                ),
            ],
            GenerationParams(temperature=0.1, max_tokens=250),
        )
        return result.text.strip()[:1500]
    except Exception as exc:  # noqa: BLE001
        logger.warning("summary_update_failed", error=str(exc)[:200])
        return old_summary
