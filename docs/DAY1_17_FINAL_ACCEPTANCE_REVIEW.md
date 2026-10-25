# API-Sentinel — Days 1–17 Acceptance Review

Audit basis: `Backend_Parsing.pdf`, repository source/tests, WSL test output and
controlled lab output available as of 2026-10-25.

This document separates repository-local evidence from requirements that need
external team components or longer live-load tests. A passing unit suite does
not by itself satisfy every operational acceptance criterion.

## Acceptance matrix

| Day | Required outcome | Evidence in this repository | Status / remaining acceptance |
|---:|---|---|---|
| 1 | Async backend, schemas and bounded queues | Schema/queue tests, FastAPI startup and queue-status tests | Repository implementation verified; no independent sign-off from the full consuming application. |
| 2 | Continuous ring-buffer consumer | Consumer validation/drop tests, capture supervisor restart/backoff tests, controlled Day 16 live capture | Controlled capture verified; sustained capture/overflow and long-run behavior still need representative load. |
| 3 | TCP/HTTP reassembly of fragmented requests/responses | TCP out-of-order/overlap tests, HTTP fragmentation, content-length, chunked and multi-message tests | Verified by automated tests; live mixed-traffic coverage remains part of Day 6. |
| 4 | Broker emits structured reconstructed transactions | Legacy per-message `http.transaction` plus completed request/response payloads for downstream topics; broker tests | Repository contract verified. PUB/SUB remains best-effort and has no durable acknowledgement. |
| 5 | Route transactions to Discovery and Heuristics | `discovery.http.transaction` and `heuristics.http.transaction` carry a complete correlated request/response pair; tests verify payloads | Partial until Member 3/4 consumers accept the exact topic/payload contract. Their services are not in this repository snapshot. |
| 6 | End-to-end capture, throughput and memory stability | Synthetic WSL run: 4,290 transactions/s; p95 0.2874 ms; p99 0.4450 ms; traced peak 1,573 KiB; 20,000 expected/published events. Separate controlled capture-to-BOLA run was observed. | Partial. Synthetic benchmark excludes live eBPF capture, reader/ring-buffer loss, ZeroMQ network delivery and database I/O. Need a sustained live WSL run with queue drops, capture rates and memory sampled. |
| 7 | Chunked, multipart and query parsing; Phase 1 freeze | Parser tests cover chunking/trailers/extensions, multipart body preservation, query preservation, body bounds and directional HEAD/1xx handling | Parser coverage verified in tests. Formal Phase 1 freeze depends on Day 5 external acceptance and Day 6 live performance acceptance. |
| 8 | Relational models for endpoints, transactions and incidents | SQLAlchemy model tests; transaction persistence now upserts discovered endpoint identity and links transaction/incident records; API integration test added | Repository-local model and endpoint linking verified in tests. No production database migration/operational acceptance claimed. |
| 9 | Request/response pairing and persistence | Correlator tests in opposite directions/FIFO, persistence worker and TransactionStore tests; Day 16 controlled transaction persistence | Verified in tests and controlled runtime. |
| 10 | Alert bus broadcasts critical events to workers/frontend | Thread-safe bounded in-process AlertBus, after-commit publication, dedup, and `/ws/alerts` endpoint with disconnect/unsubscribe tests | In-process path verified. Delivery is best-effort, bounded and non-durable; no replay or authenticated frontend integration. |
| 11 | `/api/v1/endpoints`, `/alerts`, `/metrics` | Route/OpenAPI tests; API tests use isolated SQLite; persisted transaction now creates endpoint rows | Verified in repository tests; external React UI integration is not present here. |
| 12 | Sliding-window alert deduplication | Fingerprint, window expiry/refresh, distinct event, bounded cache and metrics tests | Verified in automated tests. Suppresses notifications, not persisted incidents. |
| 13 | Standard incident schema across modules | `SecurityIncidentSchema` contract tested across BOLA, persisted incident, alert event and API serialization | Partial until Member 3/4 producers consume/emit this contract and provide compatibility evidence. |
| 14 | API route documentation/OpenAPI and Phase 2 freeze | API docs and OpenAPI contract test committed; Phase 2 review recorded | Documentation/API contract verified locally; formal Phase 2 freeze and external sign-off remain open. |
| 15 | Measure queue/serialization latency and sub-millisecond serialization | Serialization benchmarks; raw queue-wait metrics; five 500-item SQLite paced runs persisted 2,500/2,500, zero failures/rejections; paced p95 queue wait 0.028–0.056 ms | Partial. Synthetic measurements are reproducible, but the actual raw-capture queue under sustained live load, raw queue overflow and production-database behavior remain open. Preloaded-burst queue wait increases significantly as expected. |
| 16 | Capture-to-BOLA telemetry within milliseconds | Controlled live Day 16 run captured, parsed, persisted and detected BOLA with redaction checks; one observed capture-to-detection value 49.223 ms | Verified for the controlled lab scenario, not a general latency guarantee. Repeat with recorded percentiles for stronger sign-off. |
| 17 | Verdict worker updates the eBPF kernel hash map | WSL app/policy tests plus isolated veth runtime path: persisted BOLA incident, verdict accepted, map updated, active source dropped, unrelated source passed, expiry restored traffic and cleanup passed | Core controlled end-to-end path verified. The separate app-lifecycle harness still needs a successful WSL run to verify the normal FastAPI lifespan rather than manually constructing services. Production readiness/sustained latency is not claimed. |

## Latest local verification evidence

- WSL Python 3.14 full suite: 193 passed, one Starlette deprecation warning.
- Source-audit workspace full suite after additional targeted regression tests:
  200 passed (Python 3.13 audit environment).
- `compileall` and `git diff --check` passed for the audit workspace.
- The latest previously pushed baseline was synchronized at commit `661c35a`;
  follow-on acceptance fixes are not part of that commit until separately applied
  and pushed.
- GitHub Actions succeeded for the currently pushed commit, as reported by the
  repository owner. A new CI result is required after any subsequent patch is
  pushed.

## Conditions before declaring all Days 1–17 complete

1. Run the latest acceptance patch under the repository's Python 3.14 virtualenv
   and require the full suite to pass.
2. Run `scripts/day17_application_lifecycle_e2e.py` in WSL with the pinned map,
   disposable veth namespace, and experimental TC filter attached only to
   `api-sntl-test0`; record a PASS, then detach and clean up.
3. Run a sustained live-capture workload for Day 6/15 and record event/packet
   accepted, rejected and dropped counts, queue wait, throughput, and process
   memory. A synthetic benchmark is not a substitute.
4. Obtain consumer-contract acceptance from Member 3/4 for Days 5 and 13.
5. Record the formal Phase 1/Phase 2 acceptance decision for Days 7 and 14.
6. Re-run CI after the final patch and verify the pushed commit matches local
   HEAD. Do not stage local DBs, backups, or compiled binaries.
