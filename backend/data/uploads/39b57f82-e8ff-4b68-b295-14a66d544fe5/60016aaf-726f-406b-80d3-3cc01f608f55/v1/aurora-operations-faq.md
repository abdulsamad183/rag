# Aurora Operations FAQ

## How do I size a cluster?

Rule of thumb: plan for 1.6x the raw vector bytes in RAM for HNSW indexes.
A 100M collection of 768-dimensional float32 vectors is roughly 307 GB raw,
so budget about 492 GB of cluster RAM.

## What happens when a shard fails?

The Shard Manager detects a missed heartbeat after 10 seconds and promotes the
most up-to-date replica to leader. Clients retry transparently through the
Router. With the default replication factor of 3, a single node loss causes no
data loss.

## How do backups work?

Aurora writes incremental snapshots to object storage. Restores are
collection-scoped: you can restore a single collection without affecting
others. Snapshot frequency defaults to every 6 hours.

## Error codes

- `AUR-1001`: shard unavailable — the target shard has no live leader.
- `AUR-1002`: dimension mismatch — the query vector dimension does not match the collection.
- `AUR-2003`: quota exceeded — collection vector count exceeds the plan limit.
- `AUR-3staging7`: reserved for internal staging diagnostics.

## Which metric types are supported?

Cosine, dot product, and Euclidean (L2). Cosine is the default. Hamming
distance is supported only for binary-quantized collections.
