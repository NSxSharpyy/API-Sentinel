# Day 20 — Broker Buffer and High-Load Queue Tuning

## Scope

The inspected backend uses bounded Python queues and a ZeroMQ PUB/SUB
transaction broker. Redis deployment and memory configuration have not been
verified, so this work does not claim Redis tuning is complete.

## Configurable settings

| Setting | Default | Purpose |
|---|---:|---|
| `API_SENTINEL_QUEUE_MAX_SIZE` | 10000 | Raw packet, header, and metadata queue capacities |
| `API_SENTINEL_BLOCK_VERDICT_QUEUE_MAX_SIZE` | 1024 | Block/unblock verdict queue capacity |
| `API_SENTINEL_PERSISTENCE_QUEUE_MAX_SIZE` | 12000 | Persistence queue capacity |
| `API_SENTINEL_PERSISTENCE_BATCH_MAX_SIZE` | 32 | Maximum persistence batch size |
| `API_SENTINEL_ZMQ_SNDHWM` | 1000 | ZeroMQ publisher send high-water mark |
| `API_SENTINEL_ZMQ_RCVHWM` | 1000 | ZeroMQ subscriber receive high-water mark |

All integer settings must be positive. Existing defaults are preserved.
The persistence worker remains serial to avoid changing transaction ordering.

## Validation

```bash
.venv/bin/python -m pytest -q tests/test_day20_queue_tuning.py tests/test_message_broker.py tests/test_persistence_worker.py
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/day20_queue_burst.py --events 10000 --queue-capacity 512 --batch-size 32 --store-delay-ms 0.1 --burst-size 500 --burst-pause-ms 1

```

The burst benchmark uses a synthetic store. It does not verify live eBPF capture, Redis behavior, or end-to-end ZeroMQ delivery.

## Recorded synthetic burst results

Two runs offered 10,000 events with a simulated store delay of 0.1 ms.

| Queue capacity | Batch size | Accepted | Rejected | Persisted | Max depth | Throughput |
|---:|---:|---:|---:|---:|---:|---:|
| 512 | 32 | 672 | 9,328 | 672 | 512 | 5,211.35/s |
| 12,000 | 32 | 10,000 | 0 | 10,000 | 9,840 | 5,616.40/s |
| 12,000 | 128 | 10,000 | 0 | 10,000 | 9,744 | 5,611.57/s |

The 12,000-capacity runs completed without rejected or failed events.
Increasing the batch size from 32 to 128 did not improve throughput, so
the default batch size remains 32. The test is synthetic, not a live
eBPF-to-ZeroMQ soak test.

Day 20 status remains partial for requirements not verified in this
repository, including Redis memory configuration and concurrent worker
tuning. The persistence worker remains serial to preserve ordering.
