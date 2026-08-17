"""Deterministic mock LLM provider.

Enabled with ``MOCK_PROVIDER=1``. Used by the test suite and by offline demos:
it recognizes every pipeline prompt by its distinctive markers and produces
plausible, deterministic output — answers quote the actual evidence blocks,
so retrieval quality is still exercised end to end without any API key.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from app.llm.base import (
    ChatMessage,
    GenerationParams,
    GenerationResult,
    LLMProvider,
    StreamEvent,
    Usage,
)

_EVIDENCE_TAG = re.compile(r"<evidence id=(\d+)[^>]*>\n?(.*?)\n?</evidence>", re.S)
_EVIDENCE_BRACKET = re.compile(r"\[(\d+)\]\s+(.+?)(?=\n\[\d+\]|\Z)", re.S)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def _first_sentence(text: str, limit: int = 240) -> str:
    match = _SENTENCE.search(text.strip())
    sentence = match.group(0).strip() if match else text.strip()
    return sentence[:limit]


def _estimate_usage(messages: list[ChatMessage], completion: str) -> Usage:
    prompt_chars = sum(len(m.content) for m in messages)
    return Usage(prompt_tokens=max(1, prompt_chars // 4),
                 completion_tokens=max(1, len(completion) // 4))


class MockLLMProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock-small", transport: Any = None):
        super().__init__(model or "mock-small")

    async def generate(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> GenerationResult:
        text = self._respond(messages)
        return GenerationResult(
            text=text,
            usage=_estimate_usage(messages, text),
            model=self.model,
            finish_reason="stop",
            latency_ms=1,
        )

    async def stream(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncIterator[StreamEvent]:
        result = await self.generate(messages, params)
        words = result.text.split(" ")
        step = max(1, len(words) // 8)
        for start in range(0, len(words), step):
            chunk = " ".join(words[start : start + step])
            suffix = " " if start + step < len(words) else ""
            yield StreamEvent(kind="delta", text=chunk + suffix)
            await asyncio.sleep(0)
        yield StreamEvent(kind="done", usage=result.usage)

    # --- prompt dispatch -------------------------------------------------

    def _respond(self, messages: list[ChatMessage]) -> str:
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")

        if "Analyze this search query" in user:
            return self._analyze(user)
        if "alternative search queries" in user:
            return self._rewrites(user)
        if "hypothetical passage" in user:
            query = _extract(user, r"Question:\s*(.+)")
            return f"{query} The documented answer describes the mechanism in detail."
        if "Extract the factual claims" in user:
            return self._claims(user)
        if "Verify each claim" in user:
            return self._verdicts(user)
        if "Latest user question:" in user:
            query = _extract(user, r"Latest user question:\s*(.+)")
            return f'{{"standalone_query": {_json_str(query)}, "changed": false}}'
        if "rolling conversation summary" in user or "Summarize the following" in user:
            return _first_sentence(user.rsplit("\n", 1)[-1]) or "Summary of the discussion."
        if "Score every passage" in user:
            return self._rerank_scores(user)
        if "Is this evidence sufficient" in user:
            return '{"sufficient": true, "missing": "", "next_query": ""}'
        if "Write ONE search query" in user:
            query = _extract(user, r"Original question:\s*(.+)")
            return f'{{"query": {_json_str("evidence for: " + query)}}}'
        if "Extract entities and relationships" in user:
            return self._entities(user)
        if "factual contradictions" in user:
            return '{"contradictions": []}'
        if "Ground-truth answer:" in user:
            return '{"correctness": 0.9, "relevance": 0.95, "faithfulness": 0.9}'
        if "Answer the question using only this evidence" in user:
            return self._answer(user)
        return "Mock response."

    def _analyze(self, user: str) -> str:
        query = _extract(user, r"Query:\s*(.+)")
        comparison = bool(re.search(r"\b(compare|versus|vs\.?|difference|between)\b", query, re.I))
        temporal = bool(re.search(r"\b(19|20)\d{2}\b|\b(change|history|latest)\b", query, re.I))
        query_type = "comparison" if comparison else "temporal" if temporal else "simple_fact"
        return (
            f'{{"intent": "find information", "query_type": "{query_type}", '
            f'"complexity": "low", "entities": [], "time_constraints": [], '
            f'"filters": {{"author": null, "section": null, "source_type": null}}, '
            f'"expected_answer_type": "short_fact", "sub_questions": []}}'
        )

    def _rewrites(self, user: str) -> str:
        query = _extract(user, r"Query:\s*(.+)")
        variants = [f"{query} details", f"information about {query.rstrip('?')}"]
        return '{"queries": [' + ", ".join(_json_str(v) for v in variants) + "]}"

    def _claims(self, user: str) -> str:
        answer_match = re.search(r"Answer:\s*\n(.+?)\n\nReturn at most", user, re.S)
        answer = answer_match.group(1) if answer_match else user
        answer = re.sub(r"\[\d+\]", "", answer)
        sentences = [s.strip() for s in _SENTENCE.findall(answer) if len(s.strip()) > 20][:3]
        if not sentences:
            return '{"claims": []}'
        items = ", ".join(
            f'{{"text": {_json_str(s)}, "critical": {"true" if i == 0 else "false"}}}'
            for i, s in enumerate(sentences)
        )
        return f'{{"claims": [{items}]}}'

    def _verdicts(self, user: str) -> str:
        claim_count = len(re.findall(r"^\s*\d+\.\s", user, re.M)) or 1
        items = ", ".join(
            f'{{"claim_index": {i}, "verdict": "SUPPORTED", "evidence_ids": [1], '
            f'"note": "stated in evidence"}}'
            for i in range(claim_count)
        )
        return f'{{"verdicts": [{items}]}}'

    def _rerank_scores(self, user: str) -> str:
        indexes = [int(n) for n in re.findall(r"^\[(\d+)\]", user, re.M)]
        items = ", ".join(
            f'{{"id": {i}, "score": {max(1, 9 - position)}}}'
            for position, i in enumerate(indexes)
        )
        return f'{{"scores": [{items}]}}'

    def _entities(self, user: str) -> str:
        text_match = re.search(r"Text:\s*\n(.+?)\n\nExtract at most", user, re.S)
        text = text_match.group(1) if text_match else ""
        names = list(dict.fromkeys(re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", text)))[:4]
        entities = ", ".join(
            f'{{"name": {_json_str(n)}, "type": "technology", "description": ""}}' for n in names
        )
        relations = ""
        if len(names) >= 2:
            relations = (
                f'{{"source": {_json_str(names[0])}, "target": {_json_str(names[1])}, '
                f'"relation": "RELATED_TO"}}'
            )
        return f'{{"entities": [{entities}], "relations": [{relations}]}}'

    def _answer(self, user: str) -> str:
        evidence_match = re.search(r"Evidence:\s*\n(.+)\n\nAnswer the question", user, re.S)
        evidence_text = evidence_match.group(1) if evidence_match else ""
        blocks = _EVIDENCE_TAG.findall(evidence_text)
        if not blocks:
            blocks = _EVIDENCE_BRACKET.findall(evidence_text)
        if not blocks:
            return "INSUFFICIENT_EVIDENCE No evidence blocks were provided for this question."
        parts = []
        for marker, content in blocks[:2]:
            sentence = _first_sentence(content)
            if sentence:
                parts.append(f"{sentence} [{marker}]")
        return " ".join(parts) if parts else (
            "INSUFFICIENT_EVIDENCE The evidence blocks were empty."
        )


def _extract(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _json_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'
