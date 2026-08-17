# Development

## Tooling

Python is managed with **uv**. From `backend/`:

```bash
uv sync                 # install runtime + dev groups
uv run ruff check .
uv run pytest
uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run typecheck
```

## Database

```bash
docker compose up postgres redis -d
cd backend
uv run alembic upgrade head
uv run python -m app.seed
```

New migrations:

```bash
uv run python backend/scripts/gen_migration.py "add foo"
# or from backend/: uv run alembic revision --autogenerate -m "add foo"
```

Never hand-edit production schemas.

## Tests

`tests/conftest.py` starts an embedded Postgres (pgserver + pgvector) and the mock LLM/embedding providers. No API keys, no Docker required for the suite.

```bash
cd backend
uv run pytest
```

Unit tests cover parsers, chunking, fusion, routing, confidence, citations. Integration tests cover upload → ingest → retrieve → answer and evaluation runs.

## CLI

```bash
uv run rag health
uv run rag seed
uv run rag ingest ./data/demo -c "Aurora Demo"
uv run rag reindex -c "Aurora Demo"
uv run rag evaluate ./evaluation/aurora-golden.jsonl -c "Aurora Demo"
uv run rag benchmark -c "Aurora Demo"
uv run rag inspect-trace <trace-id>
```

## Inline jobs

If you do not want a worker process while iterating on the API:

```
INLINE_JOBS=true
```

Ingestion still returns immediately (asyncio background task). Redis remaining unreachable also falls back to inline execution.

## Prompts

Versioned templates live in `app/rag/prompts.py` (`query_analyzer_v1`, `answer_generator_v1`, …). Evaluation runs record the prompt version. Do not hardcode giant prompts inside random functions.
