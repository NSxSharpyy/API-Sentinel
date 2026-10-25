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
| 6 | End-to-end capture, throughput and memory stability | Controlled live WSL loopback benchmarks at 500, 1,000, 2,000, 5,000 and 10,000 HTTP requests. Final 10,000-request run persisted all 10,000 transactions at 286.6 requests/s, P95 176.292 ms, zero packet drops and zero persistence rejections; RSS growth 16.8 MiB. See `DAY1_17_ACCEPTANCE_EVIDENCE_2026-10-25.md`. | Partial. Short controlled loopback workloads pass, but long-duration stability, physical-NIC line rate and production-database behavior remain unverified. |
| 7 | Chunked, multipart and query parsing; Phase 1 freeze | Parser tests cover chunking/trailers/extensions, multipart body preservation, query preservation, body bounds and directional HEAD/1xx handling | Parser coverage verified in tests. Formal Phase 1 freeze depends on Day 5 external acceptance and Day 6 live performance acceptance. |
| 8 | Relational models for endpoints, transactions and incidents | SQLAlchemy model tests; transaction persistence now upserts discovered endpoint identity and links transaction/incident records; API integration test added | Repository-local model and endpoint linking verified in tests. No production database migration/operational acceptance claimed. |
| 9 | Request/response pairing and persistence | Correlator tests in opposite directions/FIFO, persistence worker and TransactionStore tests; Day 16 controlled transaction persistence | Verified in tests and controlled runtime. |
| 10 | Alert bus broadcasts critical events to workers/frontend | Thread-safe bounded in-process AlertBus, after-commit publication, dedup, and `/ws/alerts` endpoint with disconnect/unsubscribe tests | In-process path verified. Delivery is best-effort, bounded and non-durable; no replay or authenticated frontend integration. |
| 11 | `/api/v1/endpoints`, `/alerts`, `/metrics` | Route/OpenAPI tests; API tests use isolated SQLite; persisted transaction now creates endpoint rows | Verified in repository tests; external React UI integration is not present here. |
| 12 | Sliding-window alert deduplication | Fingerprint, window expiry/refresh, distinct event, bounded cache and metrics tests | Verified in automated tests. Suppresses notifications, not persisted incidents. |
| 13 | Standard incident schema across modules | `SecurityIncidentSchema` contract tested across BOLA, persisted incident, alert event and API serialization | Partial until Member 3/4 producers consume/emit this contract and provide compatibility evidence. |
| 14 | API route documentation/OpenAPI and Phase 2 freeze | API docs and OpenAPI contract test committed; Phase 2 review recorded | Documentation/API contract verified locally; formal Phase 2 freeze and external sign-off remain open. |
| 15 | Measure queue/serialization latency and sub-millisecond serialization | Serialization and SQLite paced benchmarks; raw-queue capacity/high-water instrumentation; live loopback runs persisted all transactions through 5,000 requests. A 10,000-request run initially rejected 1,780 jobs with a 2,500-item persistence queue; after increasing capacity to 12,000 and allowing a 60-second drain, all 10,000 persisted with zero rejections. | Partial. Controlled burst evidence is recorded; long-duration queue stability, production-database behavior and physical-NIC capture remain open. |
| 16 | Capture-to-BOLA telemetry within milliseconds | Existing controlled lab evidence records capture/parsing/persistence/BOLA detection and redaction checks. BOLA tests: 7 passed; combined detector/store/alert/API tests: 25 passed. One previously recorded capture-to-detection observation: 49.223 ms. | PARTIALLY VERIFIED. Real billing-service authorization, end-to-end dashboard delivery and a latency distribution remain unverified. Authoritative billing-service repository/setup, authorized test-account instructions and dashboard location are pending from the project team. |
| 17 | Verdict worker updates the eBPF kernel hash map | WSL app/policy tests plus isolated veth runtime path: persisted BOLA incident, verdict accepted, map updated, active source dropped, unrelated source passed, expiry restored traffic and cleanup passed | Core controlled end-to-end path verified. The FastAPI application-lifecycle test is recorded as passed in docs/DAY17_POLICY_INTEGRATION.md on 2026-10-25. This is controlled WSL lab evidence only. Production readiness/sustained latency is not claimed. |

## Latest local verification evidence

- Repository Python 3.14 full suite: **202 passed**, with one existing
  Starlette deprecation warning, after the persistence queue capacity change.
- Focused API and packet-consumer tests: **10 passed**.
- `git diff --check` passed on the source and documentation changes.
- Live WSL loopback benchmarks at 500, 1,000, 2,000 and 5,000 requests passed
  with zero reported packet drops, persistence failures or persistence rejections.
- A 10,000-request run with a 2,500-item persistence queue and 20-second drain
  failed with 1,780 persistence rejections. After increasing queue capacity
  to 12,000, the 10,000-request run with a 60-second drain persisted all
  10,000 transactions and passed the benchmark checks.
- Code and acceptance evidence are pushed to `backend-parser`. Source commit
  `e9f98de` and follow-up documentation commit `3656ce3` both passed GitHub
  Actions CI on Python 3.13 and Python 3.14.

## Conditions before declaring all Days 1–17 complete

1. **Code test gate: COMPLETE for the current commit.** The local Python 3.14
   suite passed with 202 tests. Re-run it if source code changes afterward.
2. The application-lifecycle enforcement test is recorded as passed in `docs/DAY17_POLICY_INTEGRATION.md` on 2026-10-25. Treat this as controlled WSL lab evidence, not production-readiness evidence. If rerun, preserve the isolated disposable lab setup and verify cleanup.

3. Controlled live WSL loopback runs and queue metrics are now recorded in the
   evidence report. Decide whether the remaining long-duration and production-
   database acceptance requirements need additional testing.
4. Obtain consumer-contract acceptance from Member 3/4 for Days 5 and 13.
5. Record the formal Phase 1/Phase 2 acceptance decision for Days 7 and 14.
6. **CI gate: COMPLETE for the verified commits.** GitHub Actions succeeded
   for `e9f98de` and the follow-up documentation commit `3656ce3` on Python
   3.13 and Python 3.14. For later source changes, rerun CI and verify the
   pushed commit matches local `HEAD`. Do not stage local DBs, backups,
   or compiled binaries.

## Evidence update — 2026-10-25

The latest local test and live loopback benchmark evidence is recorded in
[`DAY1_17_ACCEPTANCE_EVIDENCE_2026-10-25.md`](DAY1_17_ACCEPTANCE_EVIDENCE_2026-10-25.md).

The persistence queue capacity was increased from 2,500 to 12,000 after a
10,000-request run rejected 1,780 transactions. With the updated capacity and
a 60-second drain window, the repeated 10,000-request loopback benchmark
persisted all 10,000 transactions and reported zero packet drops, persistence
failures, or persistence rejections. The full test suite passed: 202 tests,
with one existing Starlette deprecation warning.

These results improve the local Day 6/15 evidence but do not establish
production readiness or long-duration/physical-NIC line-rate performance.
Member 3/4 acceptance for Days 5 and 13, formal Phase 1/2 decisions for Days
7 and 14, and final post-commit/push verification remain outstanding.
