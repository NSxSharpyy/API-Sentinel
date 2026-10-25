# Persistence Queue Saturation Investigation — 2026-10-25

## Problem observed

A 30-minute controlled WSL loopback soak test failed its persistence
acceptance checks:

- Successful HTTP responses: 658,632
- Persisted-record counter delta: 622,315
- Persistence queue rejections: 36,317
- Persistence failures reported by the store: 0
- Persistence queue capacity: 12,000
- Maximum observed queue depth: 12,000
- Final measured queues: empty
- Capture running at completion: true

The persistence worker used a bounded asyncio queue and non-blocking
enqueue. When full, enqueue rejected a transaction and increased its
rejection counter. The pipeline did not act on the return value.

## Implementation change

- Added a BOLA detector helper identifying login and invoice routes whose
  processing depends on detector state.
- Added a batch persistence path for ordinary transactions, sharing a
  database session and commit.
- Kept BOLA-sensitive login and invoice transactions on the individual-save
  path to preserve detector-state ordering.
- Added worker fallback to individual saves if a batch operation raises.
- Added focused tests for batch persistence, route exclusion, worker batching,
  and fallback handling.
- Queue capacity was not increased.

## Validation completed

Python compilation succeeded for the modified application modules.

Focused persistence and BOLA tests:
- 21 passed.

Full test suite:
- 206 passed.
- 1 existing Starlette/httpx test-client deprecation warning.

Short live loopback validation using the updated code and a fresh temporary
SQLite database:
- Successful HTTP responses: 1,000/1,000
- Observed persisted-record delta: 1,000
- Persistence rejections: 0
- Persistence failures: 0
- Packet drops: 0
- TCP stream-limit rejections: 0
- TCP reassembly overflows: 0
- Final raw and persistence queues: empty
- Capture running at completion: true
- Observed response rate: 274.3 requests/second
- p50 latency: 28.169 ms
- p95 latency: 42.435 ms
- p99 latency: 47.467 ms
- Sampled RSS growth: 5.2 MiB

## Limitations and follow-up

The short validation confirms the updated path processed this 1,000-request
workload without reported rejections or failures. It does not prove that
queue saturation is resolved under sustained load or that the implementation
is production-ready.

Batch commits have group rollback semantics. The worker fallback attempts
individual saves after a batch operation raises, but batch-level rollback and
recovery under real database failures remain an important behavior to verify.

These results are controlled WSL loopback and temporary-SQLite observations,
not physical-NIC line-rate or production-database benchmarks.

No further long benchmarks were run after the optimization.
