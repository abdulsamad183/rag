# Architecture

Adaptive Evidence-Driven RAG Engine is a monorepo: FastAPI backend, React frontend, PostgreSQL/pgvector, Redis, and an arq worker.

## High-level

```
┌─────────────┐     /api/v1      ┌──────────────────┐
│  React UI   │ ───────────────► │  FastAPI         │
│  Vite       │  SSE /chat/stream│  RAG orchestrator│
└─────────────┘                  └────────┬─────────┘
                                          │
            ┌──────────────┬──────────────┼──────────────┐
            ▼              ▼              ▼              ▼
     PostgreSQL+      Redis         LLM adapters     Local files
     pgvector         cache/jobs    OpenAI/Groq/     (S3-ready
     chunks/FTS       rate limits   Gemini/Ollama     storage ABC)
```

The pipeline never calls a vendor SDK directly. It talks to `LLMProvider` and `Embedder` interfaces. Swapping OpenAI for Ollama is a settings change.

## Ingestion

```
Upload → validate (type, size, path) → content-hash
      → store (filesystem ABC)
      → parse (PDF/DOCX/MD/HTML/CSV/JSON/TXT)
      → clean + structure
      → chunk (strategy per collection)
      → embed (batched, cached)
      → index (pgvector + Postgres FTS)
      → optional graph extraction
      → ready
```

HTTP returns immediately; an arq job (or inline asyncio task when Redis is down / `INLINE_JOBS=true`) does the work. Document `status` and `progress` are committed after each stage so the UI can poll honestly.

## Query pipeline

```
User query
  → conversation contextualization (pronouns / follow-ups)
  → structured query analysis (intent, type, filters)
  → retrieval router (or explicit strategy)
  → retrieve (possibly parallel queries)
  → rerank (lexical or LLM; optional)
  → evidence builder (dedupe, parent expansion, token budget)
  → generate (streaming draft)
  → claim extract + verify
  → self-correct ≤ N (gap query → retrieve → regenerate)
  → contradiction check (research/deep)
  → confidence + abstention
  → citations
```

No hidden agent loops. Every step is a named trace event with latency and a safe payload (scores, counts, decisions — never private chain-of-thought).

## Evaluation

```
JSONL dataset → EvaluationRun (config snapshot)
             → per-question RAG
             → ground-truth metrics + optional LLM judge
             → failure category
             → A/B compare / export
```

## Backend layout

```
backend/app/
  api/v1/          REST routers
  config/          Settings, model catalog, profiles
  models/          SQLAlchemy
  schemas/         Pydantic I/O
  repositories/    DB access
  services/        ingestion, chat, evaluation, graph
  llm/             provider adapters
  embeddings/
  retrieval/       strategy classes
  reranking/
  chunking/
  parsers/
  rag/             pipeline, evidence, claims, prompts
  workers/         arq tasks
  observability/   TraceRecorder
  security/
```

## Data model (core)

User → Collection → Document → DocumentVersion → Chunk (with parent_chunk_id, embedding, FTS)

Also: Conversation / Message / Citation, RetrievalTrace, EvaluationDataset / Question / Run / Result, Job, graph entities/relations.

Collections pin `embedding_provider`, `embedding_model`, `embedding_dimension`, `embedding_version`. Cross-collection search is rejected when embedding spaces differ.

## Frontend

```
frontend/src/
  api/         typed client (no raw fetch in pages)
  pages/       dashboard, chat, collections, traces, evaluation, settings
  components/  evidence, traces, confidence, graph, markdown
  state/       AppContext (providers, collections, toasts)
```

## Extension points

| Concern | Interface | MVP implementation | Later |
| --- | --- | --- | --- |
| Object storage | `BlobStore` | local filesystem | S3 / MinIO / GCS |
| Web search | `WebSearchTool` | null (disabled) | licensed search API |
| Reranker | `Reranker` | lexical, LLM | cross-encoder / GPU |
| Graph store | SQL entities | PostgreSQL | Neo4j / Neptune |
| Auth | `CurrentUser` | single default user | OIDC / RBAC |
