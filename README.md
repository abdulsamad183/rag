# Adaptive Evidence-Driven RAG Engine

A production-style retrieval and reasoning platform — not a PDF chatbot.

The system **understands the query, chooses a retrieval strategy, gathers evidence, reranks, verifies claims, estimates confidence, cites sources, and abstains when evidence is insufficient.**

```
Naive RAG
    → Hybrid Retrieval
    → Reranking
    → Adaptive Retrieval
    → Multi-Hop Retrieval
    → Evidence Verification
    → Self-Correction
    → Confidence / Abstention
    → Graph + Temporal RAG
    → Research Intelligence
```

## Why it exists

Most RAG demos retrieve a handful of chunks, dump them into a prompt, and hope. This engine is built around a different benchmark:

> Does the system retrieve the right evidence and produce answers that are actually supported by that evidence?

That means adaptive routing, hybrid search, claim verification, explicit abstention, inspectable traces, and an evaluation harness that can catch regressions.

## Features

- **Collections** with per-collection embeddings, chunking, graph, and temporal settings
- **Async ingestion** (PDF, TXT, Markdown, DOCX, HTML, CSV, JSON) with live status
- **Provider-agnostic LLMs**: OpenAI, Groq, Gemini, Ollama (and a deterministic mock for tests)
- **Retrieval strategies**: vector, BM25/keyword, hybrid (weighted + RRF), HyDE, multi-query, multi-hop, parent-child, graph, temporal, corrective, adaptive
- **Evidence-first generation** with citations, claim verification, self-correction, contradiction notes
- **Confidence + abstention** — the system is allowed to say it does not know
- **Traces** for every turn (strategy, scores, latency, tokens, cost)
- **Evaluation**: Recall@K, MRR, NDCG, faithfulness, citation metrics, abstention accuracy, A/B comparison
- **Local / privacy mode** (Ollama only, web tools off)

## Architecture

```
Frontend (React)
    → FastAPI /api/v1
        → RAG orchestrator
            → Query analysis + router
            → Retrieval strategies
            → Reranker + evidence builder
            → LLM adapter (OpenAI | Groq | Gemini | Ollama)
            → Claim verification + confidence
        → PostgreSQL + pgvector
        → Redis (jobs, cache, rate limits)
        → arq worker (ingestion, graph, eval)
```

Ingestion:

```
Upload → validate → store → parse → chunk → embed → index → ready
```

Query:

```
Query → analyze → plan → retrieve → rerank → verify → answer (or abstain)
```

Evaluation:

```
JSONL dataset → RAG configs → metrics → report / A/B
```

See [docs/architecture.md](docs/architecture.md) for diagrams and module layout.

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Pydantic Settings |
| Package manager | **uv** (not pip/requirements.txt) |
| Database | PostgreSQL + pgvector |
| Jobs / cache | Redis + arq |
| Frontend | React, TypeScript, Vite |
| Tests | pytest, ruff |

## RAG strategies

| Strategy | Path |
| --- | --- |
| Fast (Mode A) | vector → generate |
| Balanced | hybrid → rerank → generate |
| Adaptive (Mode B) | classify query → choose strategy |
| Deep / Research (Mode C) | decompose, multi-hop, verify, contradict, graph |

Full catalog: [docs/rag-strategies.md](docs/rag-strategies.md).

## Setup

```bash
cp .env.example .env
# fill OPENAI_API_KEY / GROQ_API_KEY / GEMINI_API_KEY, or use Ollama
```

### Docker (full stack)

```bash
docker compose up --build
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Postgres: localhost:5432 (rag/rag)
- Redis: localhost:6379

Seed the demo corpus (fictional Aurora docs, licensed for this repo):

```bash
docker compose exec backend uv run python -m app.seed
```

### Local development

Start Postgres + Redis (or `docker compose up postgres redis`).

```bash
# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# worker (second terminal; skip if INLINE_JOBS=true)
uv run arq app.workers.worker.WorkerSettings

# frontend
cd frontend
npm install
npm run dev
```

UI: http://localhost:5173 (Vite proxies `/api` to the backend).

```bash
uv run python -m app.seed          # demo collection + golden dataset
uv run rag health
uv run rag ingest ./data/demo -c "Aurora Demo"
uv run rag evaluate ./evaluation/aurora-golden.jsonl -c "Aurora Demo"
uv run rag benchmark -c "Aurora Demo"
uv run pytest
```

All Python commands use **uv**.

## Environment variables

See [`.env.example`](.env.example). Typed settings live in `backend/app/config/settings.py` — application code never calls `os.getenv()` directly.

Minimum to chat with a hosted model:

```env
OPENAI_API_KEY=sk-...
DEFAULT_LLM_PROVIDER=openai
DEFAULT_EMBEDDING_PROVIDER=openai
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
REDIS_URL=redis://localhost:6379/0
```

For fully local operation:

```env
LOCAL_MODE=true
DEFAULT_LLM_PROVIDER=ollama
DEFAULT_EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

## Adding providers and models

Providers implement `LLMProvider` (`generate`, `stream`, `structured_output`) and register in `app/llm/registry.py`. Embeddings are a separate adapter (`app/embeddings/`). Models are catalogued in `app/config/model_catalog.py` with capability flags (`streaming`, `json_output`, `tools`, `embeddings`, `vision`). Adding a model is a catalog entry, not a pipeline change.

Details: [docs/providers.md](docs/providers.md).

## Running evaluations

JSONL format (one object per line):

```json
{
  "question": "...",
  "expected_answer": "...",
  "relevant_documents": ["..."],
  "relevant_chunks": ["..."],
  "question_type": "multi_hop",
  "answerable": true
}
```

Upload in the Evaluation UI or:

```bash
uv run rag evaluate ./evaluation/aurora-golden.jsonl --collection "Aurora Demo" --mode adaptive
```

Metrics include Recall@K, Precision@K, MRR, NDCG, hit rate, answer F1, citation precision/recall, abstention accuracy, latency, tokens, and estimated cost. Ground-truth metrics are stored separately from optional LLM-as-judge scores.

See [docs/evaluation.md](docs/evaluation.md).

## Security

Retrieved documents are untrusted. System instructions, user queries, and evidence are separated. File uploads are type- and size-checked. Web tools (when enabled) reject private/link-local URLs. API keys never leave the backend. Details: [docs/security.md](docs/security.md).

## Roadmap

The architecture is deliberately extensible. Not all of these ship in v0.1:

- Multimodal RAG (images, tables, diagrams as first-class evidence)
- Voice interface
- Pluggable web research providers
- Native graph database backend
- Distributed indexing / GPU rerankers
- Federated knowledge bases
- Enterprise RBAC and team workspaces

Documented extension points live next to the interfaces they implement (storage, web search, rerankers, LLM providers).

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Modules, pipelines, data model |
| [docs/rag-strategies.md](docs/rag-strategies.md) | Strategy catalog and routing |
| [docs/providers.md](docs/providers.md) | LLM / embedding adapters |
| [docs/retrieval.md](docs/retrieval.md) | Vector, keyword, fusion, rerank |
| [docs/evaluation.md](docs/evaluation.md) | Datasets, metrics, baselines |
| [docs/security.md](docs/security.md) | Threat model and controls |
| [docs/deployment.md](docs/deployment.md) | Docker and production notes |
| [docs/development.md](docs/development.md) | uv, tests, migrations, CLI |

## License

Demo documents under `data/demo` are original fictional content for this project. Do not add copyrighted proprietary corpora to the seed set.
