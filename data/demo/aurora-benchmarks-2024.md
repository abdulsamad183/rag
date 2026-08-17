# Aurora Benchmark Report 2024

Published: 2024-03-15. This report covers Aurora version 2.1.

## Test Setup

Benchmarks ran on the Vv100 cluster: 8 nodes, each with 32 vCPUs and 128 GB
RAM. The dataset was SIFT-1B (1 billion 128-dimensional vectors). All numbers
use HNSW with m=16, ef_construction=200.

## Results 2024

| Metric | Value |
| --- | --- |
| Recall@10 | 0.87 |
| Median query latency | 18 ms |
| P99 query latency | 74 ms |
| Ingest throughput | 41,000 vectors/sec |
| Index build time (1B) | 11.5 hours |

In 2024, Aurora achieved 87% recall at 10 with a median latency of 18
milliseconds on SIFT-1B.

## Retention Policy 2024

The 2024 data retention policy required snapshots to be kept for **30 days**
and write-ahead logs for **7 days**. Backups older than the retention window
were deleted automatically every Sunday.

## Known Limitations in 2024

- Cross-region replication was experimental and disabled by default.
- Maximum vector dimension was 2,048.
- The Compactor could stall under sustained write loads above 50k vectors/sec.
