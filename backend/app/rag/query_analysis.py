"""Query understanding: deterministic feature extraction always runs; an LLM
pass adds semantic classification when the profile allows it. Output is
structured JSON (never free-form text) and is stored in the trace."""

from __future__ import annotations

import re
from typing import Any

from app.core.cache import cache
from app.core.logging import get_logger
from app.llm.base import ChatMessage, GenerationParams, LLMProvider
from app.observability.tracing import TraceRecorder
from app.rag import prompts
from app.utils.text import content_words, extract_acronyms, extract_quoted, extract_years

logger = get_logger("query_analysis")

_COMPARISON = re.compile(
    r"\b(compare|versus|vs\.?|difference between|better than|advantages? of .+ over)\b", re.I
)
_RELATIONSHIP = re.compile(
    r"\b(related to|relationship|depends? on|uses|authored|cites?|between .+ and)\b", re.I
)
_SUMMARIZE = re.compile(r"\b(summar(y|ize|ise)|overview|tl;?dr|key points)\b", re.I)
_MULTI_HOP_HINTS = re.compile(r"\b(led to|caused|as a result|through which|chain|then what)\b", re.I)
_LOOKUP = re.compile(r"\b(exact|specifically|error code|id|identifier|section \d+|page \d+)\b", re.I)
_TEMPORAL_WORDS = re.compile(
    r"\b(in \d{4}|before|after|between .+ and .+|changed?|history|latest|current|was|were)\b", re.I
)


def deterministic_analysis(query: str) -> dict[str, Any]:
    """Cheap, always-on features. Never wrong in a way that breaks retrieval —
    the router treats these as hints."""
    years = extract_years(query)
    quoted = extract_quoted(query)
    acronyms = extract_acronyms(query)
    words = content_words(query)
    question_marks = query.count("?")
    conjunction_load = len(re.findall(r"\b(and|or|but|while|whereas)\b", query, re.I))

    if _COMPARISON.search(query):
        query_type = "comparison"
    elif _SUMMARIZE.search(query):
        query_type = "summarization"
    elif years and _TEMPORAL_WORDS.search(query):
        query_type = "temporal"
    elif _RELATIONSHIP.search(query):
        query_type = "relationship"
    elif _MULTI_HOP_HINTS.search(query) or question_marks > 1:
        query_type = "multi_hop"
    elif _LOOKUP.search(query) or quoted:
        query_type = "specific_lookup"
    elif len(words) <= 8:
        query_type = "simple_fact"
    else:
        query_type = "analytical"

    if len(words) <= 8 and conjunction_load == 0 and question_marks <= 1:
        complexity = "low"
    elif len(words) <= 20 and conjunction_load <= 2:
        complexity = "medium"
    else:
        complexity = "high"

    return {
        "intent": "",
        "query_type": query_type,
        "complexity": complexity,
        "entities": list(dict.fromkeys(quoted + acronyms)),
        "time_constraints": [str(y) for y in years],
        "filters": {},
        "expected_answer_type": "short_fact" if query_type == "simple_fact" else "explanation",
        "sub_questions": [],
        "source": "deterministic",
    }


async def analyze_query(
    query: str,
    llm: LLMProvider | None,
    use_llm: bool,
    trace: TraceRecorder,
) -> dict[str, Any]:
    base = deterministic_analysis(query)
    if not use_llm or llm is None:
        trace.add_step("query_analysis", source="deterministic", **_safe(base))
        return base

    cached = await cache.get_rewrite("analysis", llm.model, query)
    if cached is not None:
        trace.add_step("query_analysis", source="cache", **_safe(cached))
        return cached

    try:
        result = await llm.structured_output(
            [
                ChatMessage(role="system", content=prompts.QUERY_ANALYZER_SYSTEM),
                ChatMessage(role="user", content=prompts.QUERY_ANALYZER_USER.format(query=query)),
            ],
            schema_hint=prompts.QUERY_ANALYZER_SCHEMA,
            params=GenerationParams(temperature=0.0, max_tokens=500),
        )
        usage = result.pop("_usage", None)
        if usage:
            trace.add_llm_usage(llm.name, llm.model, usage["prompt"], usage["completion"])
        merged = dict(base)
        for key in (
            "intent", "query_type", "complexity", "entities",
            "time_constraints", "filters", "expected_answer_type", "sub_questions",
        ):
            value = result.get(key)
            if value:
                merged[key] = value
        merged["source"] = "llm+deterministic"
        merged["prompt_version"] = prompts.PROMPT_VERSIONS["query_analyzer"]
        await cache.set_rewrite("analysis", llm.model, query, merged)
        trace.add_step("query_analysis", source="llm", **_safe(merged))
        return merged
    except Exception as exc:  # noqa: BLE001 — analysis must never break the pipeline
        logger.warning("llm_query_analysis_failed", error=str(exc)[:200])
        base["source"] = "deterministic_fallback"
        trace.add_step("query_analysis", source="deterministic_fallback", **_safe(base))
        return base


def _safe(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_type": analysis.get("query_type"),
        "complexity": analysis.get("complexity"),
        "entities": analysis.get("entities", [])[:8],
        "time_constraints": analysis.get("time_constraints", []),
        "sub_questions": analysis.get("sub_questions", [])[:4],
    }
