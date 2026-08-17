# Aurora Benchmark Report 2025

Published: 2025-02-20. This report covers Aurora version 3.0.

## Test Setup

Benchmarks ran on the upgraded VV200 cluster: 8 nodes, each with 48 vCPUs and
192 GB RAM. The dataset was SIFT-1B, identical to the 2024 run. Aurora 3.0
introduced the vectorized distance kernel and async prefetching.

## Results 2025

| Metric | Value |
| --- | --- |
| Recall@10 | 0.93 |
| Median query latency | 9 ms |
| P99 query latency | 41 ms |
| Ingest throughput | 88,000 vectors/sec |
| Index build time (1B) | 6.2 hours |

In 2025, Aurora achieved 93% recall at 10 with a median latency of 9
milliseconds on SIFT-1B. Note that the 2025 run used the newer VV200 hardware,
so latency numbers are not directly comparable to 2024.

## Retention Policy 2025

The retention policy changed in 2025: snapshots are now kept for **90 days**
and write-ahead logs for **14 days**. Automatic deletion runs nightly instead
of weekly.

## Improvements over 2024

- Cross-region replication became generally available.
- Maximum vector dimension increased to 4,096.
- The Compactor stall issue was fixed by the adaptive throttling scheduler.
