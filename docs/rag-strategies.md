# RAG strategies

Strategies implement `RetrievalStrategy.retrieve(query, context) -> RetrievalResult`. The router (or an explicit chat override) picks one. Profiles (`fast`, `balanced`, `adaptive`, `deep`, `research`) gate expensive behavior.

## Catalog

| Name | What it does |
| --- | --- |
| `vector` | Dense kNN over pgvector |
| `keyword` | PostgreSQL FTS / BM25-style ranking |
| `hybrid` | Weighted fusion of vector + keyword |
| `hybrid_rrf` | Reciprocal Rank Fusion of the same two lists |
| `hyde` | Generate a hypothetical passage, embed, vector search |
| `multi_query` | Expand into N paraphrases, retrieve, merge, dedupe |
| `multi_hop` | Retrieve → identify gaps → rewrite → retrieve, up to `max_hops` |
| `temporal` | Apply `valid_from` / `valid_to` / `published_at` filters |
| `graph` | Entity lookup + neighbor expansion, fused with hybrid |
| `corrective` | Retrieve, score coverage, retrieve again if weak |
| `adaptive` | Classify complexity, then delegate to one of the above |

Parent-child / hierarchical retrieval is not a separate strategy: child chunks are retrieved for precision; the evidence builder expands `parent_chunk_id` for generation context.

## Modes (UI)

| Mode | Profile | Typical path |
| --- | --- | --- |
| Fast | `fast` | vector, no rerank, no verification |
| Balanced | `balanced` | hybrid + lexical rerank |
| Adaptive | `adaptive` | LLM query analysis + router + verification |
| Deep | `deep` | multi-query / multi-hop + verify + contradictions |
| Research | `research` | deep + graph + extra correction round |

Rule-based routing is preferred when signals are clear (error codes, IDs, years). The LLM classifier is used when intent is ambiguous.

## Evidence-driven generation

Retrieval is not the answer. After candidates are selected:

1. Evidence builder drops near-duplicates and stays inside `max_context_tokens`
2. Generator must cite `[n]` markers tied to evidence rows
3. Claims are extracted and classified `SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED`
4. Unsupported critical claims trigger a bounded self-correction round
5. Confidence is a weighted mix of retrieval, rerank, coverage, claim support, contradictions, source trust
6. Below `abstain_threshold` the system returns a fixed insufficient-evidence message

## Adding a strategy

1. Implement `RetrievalStrategy` in `backend/app/retrieval/`
2. Register in `registry.STRATEGY_NAMES` and `build_strategies()`
3. Teach `app/rag/router.py` when to pick it (optional)
4. Add a unit/integration test — do not rely on the LLM to “just use it”
