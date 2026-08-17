# Retrieval

## Vector

Chunks store `embedding vector(N)` in PostgreSQL. Each collection has one dimension; IVFFlat / HNSW indexes are created to match. Queries embed with the **same** provider+model as the collection. Mismatched collections cannot be searched together.

## Keyword

Postgres full-text search (`tsvector` / `tsquery`) ranks lexical matches. This is required for error codes, model names, IDs, and other strings that embedding space smears.

## Hybrid fusion

Two lists are merged with configurable weights:

```
SEMANTIC_WEIGHT=0.7
KEYWORD_WEIGHT=0.3
```

or Reciprocal Rank Fusion (`RRF_K=60`). Weights are settings, not constants in the retriever.

## Metadata filters

`QueryFilters` (document, author, year, section, tags, source type, temporal window) are applied in SQL. The query analyzer may populate filters; the user can also pass them. Filtering is deterministic code, not an LLM.

## Reranking

Interface: `Reranker.rerank(query, chunks, top_k)`.

- `none` — skip
- `lexical` — term overlap / coverage (default, no extra model)
- `llm` — pointwise scoring with the active LLM

The system runs without a reranker; enabling one is a collection/chat option.

## Parent-child

`ParentChildChunker` (also registered as `hierarchical`) stores section-sized parents and smaller children. Retrieval hits children; `EvidenceBuilder` loads parents so the generator sees surrounding section text.

## Caching

Redis (or in-memory fallback) caches embeddings, query rewrites, and retrieval lists. Keys include collection version + embedding identity so reindex invalidates them.

## Observability

Each retrieve step writes `retrieve.<strategy>` to the trace with candidate counts and scores. The Traces UI lists them. Latency is measured per step and in total.
