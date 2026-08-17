"""Export answers, conversations, and evaluation results as Markdown/JSON/CSV."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.models import Citation, Conversation, EvaluationResult, EvaluationRun, Message


def conversation_to_markdown(
    conversation: Conversation,
    messages: list[Message],
    citations: dict[str, list[Citation]],
) -> str:
    lines = [f"# {conversation.title}", ""]
    for message in messages:
        role = "**You**" if message.role == "user" else "**Assistant**"
        lines.append(f"{role}:")
        lines.append("")
        lines.append(message.content)
        message_citations = citations.get(str(message.id), [])
        if message_citations:
            lines.append("")
            lines.append("Sources:")
            for citation in message_citations:
                location = f", p.{citation.page}" if citation.page else ""
                lines.append(f"- [{citation.marker}] {citation.document_name}{location}")
        meta = message.meta or {}
        if message.role == "assistant" and meta.get("confidence"):
            confidence = meta["confidence"]
            lines.append("")
            lines.append(
                f"> Confidence: {confidence.get('score')} ({confidence.get('level')}) · "
                f"Strategy: {meta.get('strategy', '')}"
            )
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def conversation_to_json(
    conversation: Conversation,
    messages: list[Message],
    citations: dict[str, list[Citation]],
) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "collection_ids": conversation.collection_ids,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "meta": m.meta,
                "citations": [
                    {
                        "marker": c.marker,
                        "document_name": c.document_name,
                        "page": c.page,
                        "section": c.section,
                        "snippet": c.snippet,
                        "relevance_score": c.relevance_score,
                    }
                    for c in citations.get(str(m.id), [])
                ],
            }
            for m in messages
        ],
    }


def evaluation_run_to_csv(run: EvaluationRun, results: list[EvaluationResult]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    metric_keys: list[str] = []
    for result in results:
        for key in (result.metrics or {}).get("ground_truth", {}):
            if key not in metric_keys:
                metric_keys.append(key)
    writer.writerow(["question_id", "abstained", "failure_category", "latency_ms", *metric_keys])
    for result in results:
        ground = (result.metrics or {}).get("ground_truth", {})
        writer.writerow(
            [
                str(result.question_id),
                result.abstained,
                result.failure_category,
                result.latency_ms,
                *[ground.get(k, "") for k in metric_keys],
            ]
        )
    return buffer.getvalue()


def evaluation_run_to_json(run: EvaluationRun, results: list[EvaluationResult]) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "name": run.name,
        "config": run.config,
        "status": run.status,
        "metrics": run.metrics,
        "results": [
            {
                "question_id": str(r.question_id),
                "answer": r.answer,
                "abstained": r.abstained,
                "metrics": r.metrics,
                "failure_category": r.failure_category,
                "latency_ms": r.latency_ms,
                "error": r.error,
            }
            for r in results
        ],
    }


def to_json_str(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)
