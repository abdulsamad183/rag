# Aurora Vector Database — Overview

Aurora is a fictional distributed vector database used as demo content for the
Adaptive Evidence-Driven RAG Engine. All facts in this corpus are invented.

## Architecture

Aurora consists of three core services. The **Router** accepts client queries
and forwards them to shards. The **Shard Manager** owns segment placement and
rebalancing. The **Compactor** merges immutable segments in the background.

Aurora stores vectors in HNSW graphs with configurable `m` and
`ef_construction` parameters. The default index type is HNSW; IVF-PQ is
available for memory-constrained deployments.

## Storage Engine

Segments are immutable files of at most 2 GB. Writes land in a write-ahead log
first, then flush into level-0 segments. The Compactor promotes segments
through levels L0 → L1 → L2. Deletes are tombstones resolved at compaction time.

## Consistency Model

Aurora offers eventual consistency by default. Enabling the `strict_reads`
flag routes reads through the shard leader, providing read-your-writes
consistency at roughly 1.4x read latency.

## Query Language

AuroraQL supports vector similarity search with metadata filtering:

```sql
SEARCH collection('papers')
USING vector($embedding)
WHERE year >= 2023 AND category = 'nlp'
LIMIT 10
```

## Licensing

Aurora Community Edition is Apache-2.0 licensed. Aurora Enterprise adds
role-based access control, encryption at rest, and cross-region replication.
