"""Evaluation runner: executes a dataset against a pipeline configuration,
computes ground-truth metrics (plus optional LLM-judge metrics, clearly
separated), categorizes failures, and aggregates run-level results."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.config.profiles import get_profile
from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.embeddings.registry import get_embedder
from app.evaluation import metrics as m
from app.llm.base import ChatMessage, GenerationParams
from app.llm.registry import get_llm
from app.models import (
    EvaluationDataset,
    EvaluationQuestion,
    EvaluationResult,
    EvaluationRun,
)
from app.models.base import utcnow
from app.rag.pipeline import PipelineParams, RAGPipeline
from app.repositories import collections as collection_repo

logger = get_logger("evaluation")

JUDGE_SYSTEM = (
    "You grade RAG answers. Score strictly. Respond with JSON only."
)
JUDGE_USER = """Question: {question}

Ground-truth answer: {expected}

Evidence given to the system:
{evidence}

System answer: {answer}

Score 0.0-1.0 each:
- correctness: matches the ground truth factually
- relevance: addresses the question
- faithfulness: every claim is grounded in the evidence shown"""
JUDGE_SCHEMA = '{"correctness": float, "relevance": float, "faithfulness": float}'


async def import_dataset_jsonl(
    session: AsyncSession, name: str, description: str, content: str
) -> EvaluationDataset:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValidationFailed("Dataset file is empty")
    questions: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationFailed(f"Invalid JSONL at line {line_no}: {exc}") from exc
        if "question" not in row:
            raise ValidationFailed(f"Line {line_no}: missing 'question' field")
        questions.append(row)

    dataset = EvaluationDataset(name=name, description=description, question_count=len(questions))
    session.add(dataset)
    await session.flush()
    for row in questions:
        session.add(
            EvaluationQuestion(
                dataset_id=dataset.id,
                question=str(row["question"]),
                expected_answer=str(row.get("expected_answer", "")),
                relevant_documents=list(row.get("relevant_documents", [])),
                relevant_chunks=list(row.get("relevant_chunks", [])),
                question_type=str(row.get("question_type", "simple")),
                answerable=bool(row.get("answerable", True)),
                meta={k: v for k, v in row.items() if k not in (
                    "question", "expected_answer", "relevant_documents",
                    "relevant_chunks", "question_type", "answerable",
                )},
            )
        )
    await session.commit()
    return dataset


async def run_evaluation(session: AsyncSession, run_id: uuid.UUID) -> None:
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise ValidationFailed(f"Evaluation run {run_id} not found")
    config = dict(run.config or {})
    config["_run_id"] = str(run.id)
    settings = get_settings()

    run.status = "running"
    await session.commit()

    try:
        questions = list(
            (
                await session.execute(
                    select(EvaluationQuestion).where(EvaluationQuestion.dataset_id == run.dataset_id)
                )
            ).scalars()
        )
        collection_ids = [uuid.UUID(c) for c in config.get("collection_ids", [])]
        collections = await collection_repo.get_collections(session, collection_ids)
        if not collections:
            raise ValidationFailed("Evaluation config has no collections")

        profile = get_profile(config.get("mode", "balanced"))
        semaphore = asyncio.Semaphore(settings.eval_concurrency)
        completed = 0

        async def evaluate_question(question: EvaluationQuestion) -> None:
            nonlocal completed
            async with semaphore:
                result = await _evaluate_one(question, collections, profile, config)
            session.add(result)
            completed += 1
            run.progress = completed / max(len(questions), 1)
            await session.commit()

        for question in questions:  # sequential outer loop keeps session use safe
            await evaluate_question(question)

        results = list(
            (
                await session.execute(
                    select(EvaluationResult).where(EvaluationResult.run_id == run.id)
                )
            ).scalars()
        )
        run.metrics = _aggregate(results, questions)
        run.status = "completed"
        run.completed_at = utcnow()
        await session.commit()
        logger.info("evaluation_completed", run_id=str(run_id), questions=len(questions))
    except Exception as exc:
        await session.rollback()
        run = await session.get(EvaluationRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error = str(exc)[:2000]
            await session.commit()
        raise


async def _evaluate_one(
    question: EvaluationQuestion,
    collections,
    profile,
    config: dict[str, Any],
) -> EvaluationResult:
    params = PipelineParams(
        provider=config.get("provider"),
        model=config.get("model"),
        strategy=config.get("strategy"),
        top_k=config.get("top_k"),
        rerank_top_k=config.get("rerank_top_k"),
        reranker=config.get("reranker"),
    )
    result_row = EvaluationResult(run_id=uuid.UUID(config["_run_id"]), question_id=question.id)
    try:
        embedder = get_embedder(
            collections[0].embedding_provider, collections[0].embedding_model
        )
        pipeline = RAGPipeline(
            session=None,  # replaced below
            collections=collections,
            profile=profile,
            params=params,
            embedder=embedder,
        )
        # Each question runs in its own session to isolate failures.
        from app.core.db import session_scope

        async with session_scope() as q_session:
            pipeline.session = q_session
            outcome = await pipeline.run(question.question)

        retrieved = [c.as_dict() for c in outcome.evidence]
        k = int(config.get("k", 5))
        retrieval = m.retrieval_metrics(
            retrieved, question.relevant_documents, question.relevant_chunks, k=k
        )
        answer_f1 = m.token_f1(outcome.answer, question.expected_answer)
        citation = m.citation_metrics(
            outcome.citations, question.relevant_documents, question.relevant_chunks
        )
        flags = m.relevance_flags(retrieved, question.relevant_documents, question.relevant_chunks)

        ground_truth = {
            **retrieval,
            "answer_f1": answer_f1,
            **citation,
            "abstained": outcome.abstained,
            "correct_abstention": (not question.answerable) and outcome.abstained,
            "false_answer": (not question.answerable) and not outcome.abstained,
            "confidence": outcome.confidence.score,
        }
        metrics: dict[str, Any] = {"ground_truth": ground_truth}

        if config.get("use_llm_judge") and question.expected_answer and not outcome.abstained:
            judge = await _judge(question, outcome)
            if judge:
                metrics["llm_judge"] = judge

        result_row.answer = outcome.answer
        result_row.abstained = outcome.abstained
        result_row.retrieved = retrieved[:12]
        result_row.citations = outcome.citations
        result_row.metrics = metrics
        result_row.latency_ms = outcome.trace.elapsed_ms
        result_row.failure_category = m.categorize_failure(
            answerable=question.answerable,
            abstained=outcome.abstained,
            retrieval_hit=any(flags),
            answer_f1=answer_f1,
            citation_precision=citation["citation_precision"],
            has_citations=bool(outcome.citations),
        )
        result_row.metrics["usage"] = outcome.trace.usage
    except Exception as exc:  # noqa: BLE001 — a failed question is data, not a crash
        logger.warning("evaluation_question_failed", question_id=str(question.id), error=str(exc)[:200])
        result_row.error = str(exc)[:1000]
        result_row.failure_category = "pipeline_error"
        result_row.metrics = {"ground_truth": {}}
    return result_row


async def _judge(question: EvaluationQuestion, outcome) -> dict[str, float] | None:
    settings = get_settings()
    try:
        judge_llm = get_llm(
            settings.eval_judge_provider or None, settings.eval_judge_model or None
        )
        evidence_text = "\n".join(f"[{e.marker}] {e.content[:300]}" for e in outcome.evidence[:6])
        result = await judge_llm.structured_output(
            [
                ChatMessage(role="system", content=JUDGE_SYSTEM),
                ChatMessage(
                    role="user",
                    content=JUDGE_USER.format(
                        question=question.question,
                        expected=question.expected_answer,
                        evidence=evidence_text,
                        answer=outcome.answer[:2000],
                    ),
                ),
            ],
            schema_hint=JUDGE_SCHEMA,
            params=GenerationParams(temperature=0.0, max_tokens=200),
        )
        return {
            "correctness": float(result.get("correctness", 0.0)),
            "relevance": float(result.get("relevance", 0.0)),
            "faithfulness": float(result.get("faithfulness", 0.0)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_judge_failed", error=str(exc)[:150])
        return None


def _aggregate(
    results: list[EvaluationResult], questions: list[EvaluationQuestion]
) -> dict[str, Any]:
    question_types = {str(q.id): q.question_type for q in questions}
    ground: dict[str, list[float]] = {}
    judge: dict[str, list[float]] = {}
    by_type: dict[str, dict[str, list[float]]] = {}
    failures: dict[str, int] = {}
    latencies: list[int] = []
    total_cost = 0.0
    total_tokens = 0

    for result in results:
        gt = (result.metrics or {}).get("ground_truth", {})
        for key, value in gt.items():
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            if isinstance(value, int | float):
                ground.setdefault(key, []).append(float(value))
                qtype = question_types.get(str(result.question_id), "simple")
                by_type.setdefault(qtype, {}).setdefault(key, []).append(float(value))
        for key, value in (result.metrics or {}).get("llm_judge", {}).items():
            if isinstance(value, int | float):
                judge.setdefault(key, []).append(float(value))
        if result.failure_category:
            failures[result.failure_category] = failures.get(result.failure_category, 0) + 1
        latencies.append(result.latency_ms)
        usage = (result.metrics or {}).get("usage", {})
        total_cost += float(usage.get("estimated_cost_usd", 0.0))
        total_tokens += int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    unanswerable = [r for r in results if not _answerable(r, questions)]
    abstention_accuracy = (
        mean([1.0 if r.abstained else 0.0 for r in unanswerable]) if unanswerable else None
    )

    return {
        "ground_truth": {k: mean(v) for k, v in ground.items()},
        "llm_judge": {k: mean(v) for k, v in judge.items()},
        "by_question_type": {
            qtype: {k: mean(v) for k, v in metrics.items()} for qtype, metrics in by_type.items()
        },
        "failures": failures,
        "abstention_accuracy": abstention_accuracy,
        "latency_ms": {
            "mean": int(mean([float(x) for x in latencies])),
            "p95": int(sorted(latencies)[int(len(latencies) * 0.95) - 1]) if latencies else 0,
        },
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 6),
        "questions": len(results),
        "errors": sum(1 for r in results if r.error),
    }


def _answerable(result: EvaluationResult, questions: list[EvaluationQuestion]) -> bool:
    for question in questions:
        if question.id == result.question_id:
            return question.answerable
    return True
