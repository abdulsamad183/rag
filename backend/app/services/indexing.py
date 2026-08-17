"""Vector index management.

Chunks use an untyped pgvector column so different collections can use
different embedding dimensions. ANN indexes require a fixed dimension, so we
create one partial HNSW expression index per dimension in use:

    CREATE INDEX ... USING hnsw ((embedding::vector(D)) vector_cosine_ops)

Failure to create an index degrades to exact scans (correct, slower) and is
logged, never fatal.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger("indexing")


async def ensure_vector_index(session: AsyncSession, dimension: int) -> None:
    if dimension <= 0 or dimension > 4000:
        return
    index_name = f"ix_chunks_embedding_hnsw_{dimension}"
    ddl = text(
        f"CREATE INDEX IF NOT EXISTS {index_name} ON chunks "
        f"USING hnsw ((embedding::vector({dimension})) vector_cosine_ops) "
        f"WITH (m = 16, ef_construction = 64)"
    )
    try:
        await session.execute(ddl)
        logger.info("vector_index_ready", dimension=dimension)
    except Exception as exc:  # noqa: BLE001 — exact scan fallback is acceptable
        logger.warning("vector_index_creation_failed", dimension=dimension, error=str(exc)[:200])
