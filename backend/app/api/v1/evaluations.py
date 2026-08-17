from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.errors import NotFoundError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models import EvaluationDataset, EvaluationQuestion, EvaluationResult, EvaluationRun
from app.schemas.common import OkResponse
from app.schemas.evaluations import (
    DatasetOut,
    QuestionOut,
    ResultOut,
    RunComparison,
    RunCreate,
    RunOut,
)
from app.services.evaluation import import_dataset_jsonl
from app.services.export import evaluation_run_to_csv, evaluation_run_to_json, to_json_str
from app.workers.queue import enqueue

router = APIRouter(prefix="/evaluations", tags=["evaluation"])


@router.post("/datasets", response_model=DatasetOut, status_code=201,
             dependencies=[Depends(rate_limiter("default"))])
async def upload_dataset(
    session: DbSession,
    file: UploadFile = File(..., description="JSONL: one question object per line"),
    name: str = Form(...),
    description: str = Form(default=""),
) -> DatasetOut:
    content = (await file.read()).decode("utf-8", errors="replace")
    existing = await session.execute(
        select(EvaluationDataset).where(EvaluationDataset.name == name)
    )
    if existing.scalars().first() is not None:
        raise ValidationFailed(f"Dataset '{name}' already exists")
    dataset = await import_dataset_jsonl(session, name, description, content)
    return DatasetOut.model_validate(dataset)


@router.get("/datasets", response_model=list[DatasetOut])
async def list_datasets(session: DbSession) -> list[DatasetOut]:
    datasets = (
        (await session.execute(select(EvaluationDataset).order_by(EvaluationDataset.created_at.desc())))
        .scalars().all()
    )
    return [DatasetOut.model_validate(d) for d in datasets]


@router.get("/datasets/{dataset_id}/questions", response_model=list[QuestionOut])
async def list_questions(dataset_id: uuid.UUID, session: DbSession) -> list[QuestionOut]:
    questions = (
        (
            await session.execute(
                select(EvaluationQuestion).where(EvaluationQuestion.dataset_id == dataset_id)
            )
        ).scalars().all()
    )
    return [QuestionOut.model_validate(q) for q in questions]


@router.delete("/datasets/{dataset_id}", response_model=OkResponse)
async def delete_dataset(dataset_id: uuid.UUID, session: DbSession) -> OkResponse:
    dataset = await session.get(EvaluationDataset, dataset_id)
    if dataset is None:
        raise NotFoundError("Dataset not found")
    await session.delete(dataset)
    await session.commit()
    return OkResponse()


@router.post(
    "/datasets/{dataset_id}/runs",
    response_model=RunOut,
    status_code=201,
    dependencies=[Depends(rate_limiter("evaluations"))],
)
async def create_run(dataset_id: uuid.UUID, payload: RunCreate, session: DbSession) -> RunOut:
    dataset = await session.get(EvaluationDataset, dataset_id)
    if dataset is None:
        raise NotFoundError("Dataset not found")
    run = EvaluationRun(
        dataset_id=dataset_id,
        name=payload.name or f"{dataset.name} run",
        config={
            "collection_ids": [str(c) for c in payload.collection_ids],
            "provider": payload.provider,
            "model": payload.model,
            "mode": payload.mode,
            "strategy": payload.strategy,
            "top_k": payload.top_k,
            "rerank_top_k": payload.rerank_top_k,
            "reranker": payload.reranker,
            "k": payload.k,
            "use_llm_judge": payload.use_llm_judge,
        },
        status="queued",
    )
    session.add(run)
    await session.commit()
    await enqueue("run_evaluation", run_id=str(run.id))
    return RunOut.model_validate(run)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(session: DbSession, dataset_id: uuid.UUID | None = None) -> list[RunOut]:
    stmt = select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(100)
    if dataset_id is not None:
        stmt = stmt.where(EvaluationRun.dataset_id == dataset_id)
    runs = (await session.execute(stmt)).scalars().all()
    return [RunOut.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, session: DbSession) -> RunOut:
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise NotFoundError("Run not found")
    return RunOut.model_validate(run)


@router.get("/runs/{run_id}/results", response_model=list[ResultOut])
async def get_run_results(run_id: uuid.UUID, session: DbSession) -> list[ResultOut]:
    results = (
        (
            await session.execute(
                select(EvaluationResult).where(EvaluationResult.run_id == run_id)
            )
        ).scalars().all()
    )
    question_ids = {r.question_id for r in results}
    questions: dict[uuid.UUID, EvaluationQuestion] = {}
    if question_ids:
        rows = (
            await session.execute(
                select(EvaluationQuestion).where(EvaluationQuestion.id.in_(question_ids))
            )
        ).scalars().all()
        questions = {q.id: q for q in rows}

    outs: list[ResultOut] = []
    for result in results:
        out = ResultOut.model_validate(result)
        question = questions.get(result.question_id)
        if question is not None:
            out.question = question.question
            out.expected_answer = question.expected_answer
            out.question_type = question.question_type
            out.answerable = question.answerable
        outs.append(out)
    return outs


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: uuid.UUID, session: DbSession, format: Literal["csv", "json"] = "json"
) -> Response:
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise NotFoundError("Run not found")
    results = (
        (await session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run_id)))
        .scalars().all()
    )
    if format == "csv":
        return Response(
            content=evaluation_run_to_csv(run, list(results)),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="run-{run_id}.csv"'},
        )
    return Response(
        content=to_json_str(evaluation_run_to_json(run, list(results))),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}.json"'},
    )


@router.get("/compare", response_model=RunComparison)
async def compare_runs(session: DbSession, run_ids: str) -> RunComparison:
    """A/B comparison: ?run_ids=<id1>,<id2>[,<id3>…]"""
    try:
        ids = [uuid.UUID(part.strip()) for part in run_ids.split(",") if part.strip()]
    except ValueError as exc:
        raise ValidationFailed("run_ids must be comma-separated UUIDs") from exc
    if len(ids) < 2:
        raise ValidationFailed("Provide at least two run ids to compare")

    runs = []
    for run_id in ids:
        run = await session.get(EvaluationRun, run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")
        runs.append(run)

    metric_table: dict[str, dict[str, float | None]] = {}
    for run in runs:
        ground = (run.metrics or {}).get("ground_truth", {})
        extras = {
            "abstention_accuracy": (run.metrics or {}).get("abstention_accuracy"),
            "latency_ms_mean": ((run.metrics or {}).get("latency_ms") or {}).get("mean"),
            "total_tokens": (run.metrics or {}).get("total_tokens"),
            "estimated_cost_usd": (run.metrics or {}).get("estimated_cost_usd"),
        }
        for key, value in {**ground, **extras}.items():
            if isinstance(value, int | float) or value is None:
                metric_table.setdefault(key, {})[str(run.id)] = value

    return RunComparison(runs=[RunOut.model_validate(r) for r in runs], metric_table=metric_table)
