# Day 15 — File-Backed SQLite Persistence and Bounded Queue Audit

Audit date: 2026-10-25

Command:

```bash
python benchmarks/benchmark_sqlite_persistence.py \
  --items 100 --repeats 2 --queue-capacity 100 --producer-delay-ms 0.2
```

This benchmark uses a temporary file-backed SQLite database and the actual
SQLAlchemy `TransactionStore` and `TransactionPersistenceWorker`, not a fake
store. It runs a preloaded burst, an overload/rejection case, and a finite paced
producer while the consumer is running. It is still a local SQLite benchmark,
not PostgreSQL or production workload validation.

## Results summary

| Scenario | Attempts | Accepted / persisted | Rejected | DB row check | p95 queue wait |
|---|---:|---:|---:|---|---:|
| Preloaded burst, run 1 | 100 | 100 | 0 | 100 rows; matched | 319.40 ms |
| Preloaded burst, run 2 | 100 | 100 | 0 | 100 rows; matched | 293.12 ms |
| Bounded queue saturation, run 1 | 200 | 100 | 100 | 100 rows; matched | 297.11 ms |
| Bounded queue saturation, run 2 | 200 | 100 | 100 | 100 rows; matched | 302.07 ms |
| Concurrent paced producer-consumer, run 1 | 100 | 100 | 0 | 100 rows; matched | 210.78 ms |
| Concurrent paced producer-consumer, run 2 | 100 | 100 | 0 | 100 rows; matched | 219.94 ms |

No save failures or database row-count mismatches occurred. The saturation test
confirmed the queue capacity of 100: the 100 excess burst jobs were rejected
and the 100 accepted jobs were persisted.

## Interpretation and acceptance

The large queue-wait values are expected for a preloaded 100-item queue with
serial SQLite transactions; this run is evidence that queue wait can grow under
backlog, not proof that the target latency is met. The existing serialization
benchmark results are separate: those synthetic serialization runs remained
below 1 ms at aggregate p95 for the tested body sizes.

**Partial.** File-backed SQLite persistence and controlled queue saturation are
now measured. Remaining work: run against the configured target database, test
longer sustained producer-consumer load and burst sizes representative of live
capture, measure raw packet queue overflow behavior in the target WSL pipeline,
and compare results with agreed acceptance thresholds.

## Repeatability run — 2026-10-25, WSL Python 3.14

Configuration: 500 paced items per repeat, five repeats, queue capacity 100, producer delay 5 ms, file-backed temporary SQLite.

### Paced producer-consumer results

| Run | Accepted | Persisted / DB rows | Rejected | Failed | Average queue wait (ms) | p95 queue wait (ms) | Maximum queue wait (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 500 | 500 | 0 | 0 | 0.023816 | 0.056204 | 0.092184 |
| 2 | 500 | 500 | 0 | 0 | 0.025866 | 0.045129 | 0.205353 |
| 3 | 500 | 500 | 0 | 0 | 0.020899 | 0.028421 | 0.127267 |
| 4 | 500 | 500 | 0 | 0 | 0.021397 | 0.031771 | 0.050309 |
| 5 | 500 | 500 | 0 | 0 | 0.022018 | 0.034610 | 0.063840 |

All five paced runs reconciled 500 accepted jobs with 500 persisted rows and reported zero worker failures or rejections. The observed p95 queue wait ranged from 0.028421 to 0.056204 ms.

### Queue-capacity behavior

In each preloaded-burst scenario, 500 jobs were attempted, 100 accepted, 400 rejected, and 100 persisted with zero worker failures. In each bounded saturation scenario, 1,000 jobs were attempted, 100 accepted, 900 rejected, and 100 persisted with zero worker failures. The rejections are expected when the capacity-100 queue is full.

Preloaded-burst p95 queue wait ranged from approximately 75.2 to 99.8 ms, showing the expected effect of backlog. These synthetic results do not establish production-database performance, sustained high-load behavior, or live raw-packet queue overflow behavior.
