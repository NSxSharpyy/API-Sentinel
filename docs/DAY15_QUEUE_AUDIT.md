# Day 15 — Persistence Queue Wait Audit

## Purpose

Measure persistence queue wait separately from serialization and database
processing. The measurement boundary is the job's monotonic enqueue
timestamp to the worker's dequeue-time observation.

## Environment and method

- Runtime: Python 3.14.4 on Linux/WSL2.
- Clock: `time.perf_counter_ns()`.
- Queue: `TransactionPersistenceWorker` with a bounded `asyncio.Queue`.
- Workload: 200 jobs preloaded before the consumer starts.
- Repetitions: 3 for each scenario.
- Store: synthetic; no real database I/O.
- Saturation scenario: 400 enqueue attempts with capacity 200.
- Expected full-queue warnings were suppressed only during saturation setup.

This is a preloaded-burst test. It is not a sustained producer-consumer test,
a real SQLite benchmark, or a production throughput measurement.

## Results

### Immediate synthetic save

| Run | Average wait (ms) | p95 wait (ms) | Maximum wait (ms) | Drain time (ms) |
|---:|---:|---:|---:|---:|
| 1 | 11.350 | 20.322 | 21.268 | 21.341 |
| 2 | 9.748 | 18.318 | 19.256 | 19.316 |
| 3 | 9.846 | 18.618 | 19.543 | 19.616 |

All 200 jobs were accepted and drained in each run; no failures occurred.

### Synthetic store with a configured 0.5 ms blocking delay

| Run | Average wait (ms) | p95 wait (ms) | Maximum wait (ms) | Drain time (ms) |
|---:|---:|---:|---:|---:|
| 1 | 72.985 | 138.122 | 145.128 | 145.896 |
| 2 | 72.757 | 137.665 | 144.650 | 145.345 |
| 3 | 72.884 | 137.469 | 144.432 | 145.221 |

All 200 jobs were accepted and drained in each run; no failures occurred.
Drain time includes the worker's thread-offload and scheduling overhead,
not just the configured sleep delay.

### Full queue and rejection behavior

| Run | Attempts | Accepted | Rejected | p95 wait (ms) | Drain time (ms) |
|---:|---:|---:|---:|---:|---:|
| 1 | 400 | 200 | 200 | 137.236 | 144.920 |
| 2 | 400 | 200 | 200 | 137.479 | 145.235 |
| 3 | 400 | 200 | 200 | 137.907 | 145.595 |

All accepted jobs drained successfully. The queue rejected the additional
200 submissions per run because its capacity was 200.

## Interpretation and limitations

Queue wait increased substantially when the worker performed a blocking
synthetic save for each dequeued job. This reflects backlog behavior with a
single consumer in this test setup. The synthetic store does not model actual
database latency, locking, disk I/O, or transaction contention.

The measurement covers enqueue-to-dequeue wait. It excludes the subsequent
database-save duration. Because the queue is preloaded before the consumer
starts, the results include producer burst-fill time and are not representative
of every live arrival pattern.

## Day 15 status

- Serialization: two independent runs showed aggregate p95 below 1 ms for
  synthetic request bodies of 0, 1,024, 8,192 and 32,768 bytes.
- Persistence queue: preloaded-burst wait and bounded-queue rejection measured.
- Still outstanding: real-database performance, sustained producer-consumer
  load, and raw packet queue wait/saturation measurements.
- Overall status: Partial pending broader queue and database validation.
