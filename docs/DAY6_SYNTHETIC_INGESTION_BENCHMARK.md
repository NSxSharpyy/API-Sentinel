# Day 6 — Synthetic Ingestion Throughput and Traced Memory

Audit date: 2026-10-25
Command:

```bash
python benchmarks/benchmark_ingestion_pipeline.py --iterations 10000 --warmup 1000
```

## Single controlled run

Environment: Python 3.13.5 in the source-audit container; `tracemalloc` enabled.
The benchmark exercises HTTP parsing, request/response correlation and JSON
serialization to a discard sink. It intentionally excludes eBPF capture,
ring-buffer reads, production ZeroMQ network delivery, and database persistence.

| Metric | Observed value |
|---|---:|
| Warm-up transactions | 1,000 |
| Measured transactions | 10,000 |
| Published events | 20,000 (expected count matched) |
| Serialized payload bytes | 6,540,000 |
| Throughput | 2,678.7 transactions/s |
| Per-transaction p50 | 0.3087 ms |
| Per-transaction p95 | 0.6358 ms |
| Per-transaction p99 | 1.1782 ms |
| Traced current memory after run | 1,532.2 KiB |
| Traced peak memory during run | 1,535.7 KiB |
| Completed transaction history capacity | 1,000 |

## Interpretation

This is reproducible application-level evidence for the parser/correlator and
serialization path under a synthetic workload. The bounded completion history
remained at its configured 1,000-item capacity during the measured run.
The observed p99 latency was above 1 ms, and the results are from one local run.

## Acceptance status

**Partial.** This benchmark does not establish line-rate eBPF capture, ring-buffer
loss behavior, memory stability under a sustained live attack stream, or full
network/database pipeline throughput. Re-run it in the target WSL environment
and collect live capture counters before claiming the original Day 6 requirement
fully complete.

## Additional WSL result — 2026-10-25

Environment: user's WSL checkout with Python 3.14.

- Iterations: 10,000; warm-up: 1,000.
- Throughput: 4,290 transactions/s and 8,580 events/s.
- Event reconciliation: 20,000 expected and published events.
- Serialized payload: 6,540,000 bytes.
- Per-transaction latency: p50 0.2225 ms, p95 0.2874 ms, p99 0.4450 ms.
- Traced memory: 1,569.6 KiB current and 1,573.0 KiB peak.
- Completed-transaction history capacity: 1,000.

This is a synthetic parser/correlator/serialization result. It excludes live eBPF capture, TCP ring-buffer consumption, network ZeroMQ delivery, and database I/O. It does not demonstrate line-rate capture or sustained-load memory stability.
