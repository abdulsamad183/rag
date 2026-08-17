# Evaluation

## Dataset format (JSONL)

```json
{
  "question": "What recall at 10 did Aurora achieve in 2024?",
  "expected_answer": "0.87 recall@10 on SIFT-1B",
  "relevant_documents": ["Aurora Benchmark Report 2024"],
  "relevant_chunks": ["Recall@10 | 0.87"],
  "question_type": "temporal",
  "answerable": true
}
```

Unanswerable items set `"answerable": false` and empty relevant lists. Those measure **correct abstention**, not answer F1.

A golden set ships at `evaluation/aurora-golden.jsonl` against the fictional Aurora demo corpus.

## Retrieval metrics

Computed against `relevant_documents` / `relevant_chunks` probes:

- Recall@K, Precision@K
- MRR, NDCG, hit rate

Broken out by `question_type` (`simple`, `comparison`, `multi_hop`, `temporal`, `unanswerable`).

## Generation metrics

When `expected_answer` is present: token-overlap F1 (not LLM-as-judge). Optional judge scores (`faithfulness`, `answer_relevance`, `context_relevance`) are stored under `metrics.llm_judge` and never mixed into `metrics.ground_truth`.

## Citation metrics

A citation is correct if the cited chunk actually contains supporting text (probe overlap). Reported: precision, recall, completeness.

## Abstention metrics

- Correct abstention rate on `answerable=false`
- False-answer rate (answered when it should have refused)

## Baselines

`uv run rag benchmark -c "Aurora Demo"` runs:

1. Vector RAG (fast / vector)
2. Hybrid RAG
3. Hybrid + reranker
4. Adaptive Evidence-Driven (the system)

and prints retrieval quality, answer F1, citation precision, abstention, latency, tokens, cost.

Each `EvaluationRun` snapshots chunking, embedding model, strategy, reranker, provider, model, and prompt versions for reproducibility.

## Failure analysis

Per-question `failure_category`:

`retrieval_failure` · `generation_failure` · `citation_failure` · `abstention_failure` · `pipeline_error`

The Evaluation → run page lists them and opens retrieved evidence + the trace.
