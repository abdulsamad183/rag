"""Evaluation runner end-to-end with the mock pipeline."""

import asyncio
import uuid

from sqlalchemy import select

from app.core.db import session_scope
from app.models import Collection, EvaluationResult, EvaluationRun
from app.repositories.users import get_or_create_default_user
from app.services.documents import upload_document
from app.services.evaluation import import_dataset_jsonl, run_evaluation
from app.services.ingestion import ingest_document

CORPUS = (
    "# Aurora Report\n\nIn 2024, Aurora achieved 87 percent recall at 10.\n\n"
    "The retention policy keeps snapshots for 30 days.\n"
)

DATASET_JSONL = "\n".join(
    [
        '{"question": "What recall did Aurora achieve in 2024?", '
        '"expected_answer": "Aurora achieved 87 percent recall at 10 in 2024.", '
        '"relevant_documents": ["report.md"], "relevant_chunks": ["87 percent recall"], '
        '"question_type": "simple", "answerable": true}',
        '{"question": "What is the price of Aurora Enterprise?", "expected_answer": "", '
        '"relevant_documents": [], "relevant_chunks": [], '
        '"question_type": "unanswerable", "answerable": false}',
    ]
)


async def test_import_and_run_evaluation(database):
    async with session_scope() as session:
        user = await get_or_create_default_user(session)
        collection = Collection(
            user_id=user.id,
            name=f"eval-{uuid.uuid4().hex[:8]}",
            embedding_provider="mock",
            embedding_model="mock-embed",
            chunking_config={"strategy": "markdown", "chunk_size": 400, "chunk_overlap": 50},
        )
        session.add(collection)
        await session.commit()
        document, _ = await upload_document(session, collection, "report.md", CORPUS.encode())
        await ingest_document(session, document.id)

        dataset = await import_dataset_jsonl(session, "golden-mini", "test", DATASET_JSONL)
        assert dataset.question_count == 2

        run = EvaluationRun(
            dataset_id=dataset.id,
            name="mock run",
            config={
                "collection_ids": [str(collection.id)],
                "mode": "fast",
                "provider": "mock",
                "k": 5,
            },
        )
        session.add(run)
        await session.commit()

        await run_evaluation(session, run.id)
        await session.refresh(run)

        assert run.status == "completed"
        metrics = run.metrics
        assert "ground_truth" in metrics
        assert metrics["questions"] == 2
        # the answerable question must be retrievable with mock embeddings
        assert metrics["ground_truth"].get("recall@5", 0) > 0

        results = (
            (await session.execute(
                select(EvaluationResult).where(EvaluationResult.run_id == run.id)
            )).scalars().all()
        )
        assert len(results) == 2
        for row in results:
            assert row.latency_ms >= 0
            assert "ground_truth" in (row.metrics or {})


async def test_dataset_import_rejects_garbage(database):
    async with session_scope() as session:
        try:
            await import_dataset_jsonl(session, "bad", "", "not json at all\n{broken")
            raised = False
        except Exception:  # noqa: BLE001
            raised = True
        assert raised
