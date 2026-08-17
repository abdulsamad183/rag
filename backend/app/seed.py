"""Seed development data: default user, demo collection, demo documents,
and the golden evaluation dataset.

    uv run python -m app.seed
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.embeddings.registry import default_embedding_model
from app.models import Collection, EvaluationDataset
from app.repositories.users import get_or_create_default_user
from app.services.documents import upload_document
from app.services.evaluation import import_dataset_jsonl
from app.services.ingestion import ingest_document

logger = get_logger("seed")

DEMO_COLLECTION = "Aurora Demo"


def _first_existing(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]  # .../adaptive-rag  (app/seed.py → app → backend → repo)
_BACKEND_ROOT = _HERE.parents[1]
DEMO_DIR = _first_existing(
    _REPO_ROOT / "data" / "demo",
    _BACKEND_ROOT / "data" / "demo",
    Path("/data/demo"),
)
GOLDEN_DATASET = _first_existing(
    _REPO_ROOT / "evaluation" / "aurora-golden.jsonl",
    _BACKEND_ROOT / "evaluation" / "aurora-golden.jsonl",
    Path("/evaluation/aurora-golden.jsonl"),
)

DOC_META = {
    "aurora-benchmarks-2024.md": {
        "published_at": "2024-03-15T00:00:00+00:00",
        "valid_from": "2024-01-01T00:00:00+00:00",
        "valid_to": "2024-12-31T23:59:59+00:00",
        "tags": ["benchmark"],
    },
    "aurora-benchmarks-2025.md": {
        "published_at": "2025-02-20T00:00:00+00:00",
        "valid_from": "2025-01-01T00:00:00+00:00",
        "tags": ["benchmark"],
    },
    "aurora-overview.md": {"tags": ["docs"]},
    "aurora-operations-faq.md": {"tags": ["docs", "faq"]},
}


async def seed(ingest: bool = True) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)

    async with session_scope() as session:
        user = await get_or_create_default_user(session)

        existing = await session.execute(
            select(Collection).where(Collection.user_id == user.id, Collection.name == DEMO_COLLECTION)
        )
        collection = existing.scalars().first()
        if collection is None:
            provider = settings.default_embedding_provider
            if settings.local_mode:
                provider = "ollama"
            collection = Collection(
                user_id=user.id,
                name=DEMO_COLLECTION,
                description="Fictional Aurora vector-database docs for demos and evaluation.",
                embedding_provider=provider,
                embedding_model=default_embedding_model(provider),
                chunking_config={"strategy": "markdown", "chunk_size": 800, "chunk_overlap": 120},
                temporal_enabled=True,
            )
            session.add(collection)
            await session.commit()
            logger.info("collection_created", name=DEMO_COLLECTION)
        else:
            logger.info("collection_exists", name=DEMO_COLLECTION)

        document_ids = []
        for path in sorted(DEMO_DIR.glob("*.md")):
            document, is_new = await upload_document(
                session, collection, path.name, path.read_bytes(), DOC_META.get(path.name, {})
            )
            if is_new:
                document_ids.append(document.id)
                logger.info("document_uploaded", filename=path.name)
            elif document.status in ("failed", "queued"):
                document_ids.append(document.id)
                logger.info("document_reingest", filename=path.name, status=document.status)
            else:
                logger.info("document_unchanged", filename=path.name)

        if ingest:
            for document_id in document_ids:
                try:
                    await ingest_document(session, document_id)
                except Exception as exc:  # noqa: BLE001
                    logger.error("seed_ingestion_failed", document_id=str(document_id),
                                 error=str(exc)[:200])

        dataset_name = "Aurora Golden v1"
        existing_ds = await session.execute(
            select(EvaluationDataset).where(EvaluationDataset.name == dataset_name)
        )
        if existing_ds.scalars().first() is None and GOLDEN_DATASET.exists():
            await import_dataset_jsonl(
                session,
                dataset_name,
                "Golden regression dataset for the Aurora demo corpus "
                "(answerable + unanswerable questions).",
                GOLDEN_DATASET.read_text(),
            )
            logger.info("dataset_imported", name=dataset_name)

    logger.info("seed_complete")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
