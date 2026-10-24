# Day 15 — Raw Packet Queue Wait Audit

## Purpose

Measure raw-packet enqueue-to-dequeue wait separately from packet processing.

## Method and environment

- Runtime: Python 3.14.4 on Linux/WSL2.
- Clock: `time.perf_counter_ns()`.
- Producer: `consume_events()` from `app/ring_buffer_consumer.py`.
- Consumer: `packet_worker()` from `app/packet_worker.py`.
- Workload: 200 synthetic UDP packets preloaded before starting the worker.
- Repetitions: 3.
- The worker skips UDP packets after dequeue; no TCP reassembly, HTTP parsing,
  capture process, or database I/O is included.

## Results

| Run | Accepted | Initial queue depth | Average wait (ms) | p95 wait (ms) | Maximum wait (ms) | Drain time (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 200 | 200 | 1.106 | 1.188 | 1.205 | 1.024 |
| 2 | 200 | 200 | 0.913 | 0.997 | 1.014 | 0.821 |
| 3 | 200 | 200 | 0.905 | 0.973 | 0.985 | 0.822 |

Each run produced 200 queue-wait samples. The pipeline received zero feed
calls, as expected for this UDP workload.

## Interpretation and limitations

The first run's p95 was above 1 ms; the next two were below 1 ms. This is
evidence of variation around the target, not a consistent sub-millisecond
guarantee.

The queue was filled before the worker started. The test does not establish
sustained-load latency, packet-drop behavior under overflow, real capture
performance, TCP processing cost, or end-to-end processing latency.

## Day 15 status

- Serialization: aggregate p95 below 1 ms across four synthetic body sizes
  in two independent benchmark invocations.
- Persistence queue: preloaded-burst enqueue-to-dequeue wait and bounded
  queue rejection measured with a synthetic store.
- Raw packet queue: preloaded 200-packet burst measured in three runs.
- Outstanding: real-database performance, sustained producer-consumer load,
  raw packet queue overflow behavior, and broader concurrency validation.
- Overall status: Partial.
