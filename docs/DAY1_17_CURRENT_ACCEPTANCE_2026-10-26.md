# API-Sentinel — Current Day 1–17 Acceptance Status

Audit date: 2026-10-26
Branch: `backend-parser`
Source of truth: `Backend_Parsing.pdf`
Reviewed commit: `53ad9e9701bc88a240889e1e42ff6448508ef8b3`

This report supersedes older test counts and baseline references in the
historical Day 1–17 trackers. It distinguishes repository implementation,
controlled-lab evidence, and external acceptance.

## Latest verified evidence

- Commit `53ad9e9` was pushed to `origin/backend-parser`.
- GitHub Actions Python tests run #10 passed for `53ad9e9` in 33 seconds.
- Local full test suite: **206 passed, 1 existing deprecation warning**.
- Focused persistence and BOLA suite: **21 passed**.
- Python compilation and `git diff --check` passed.
- Post-change live loopback validation: **1,000/1,000 HTTP responses succeeded
  and 1,000 persisted records were observed**. Persistence rejections, reported
  persistence failures, and packet drops were zero; measured queues drained to
  zero and capture remained running.
- The short validation used a fresh temporary SQLite database. It is not a
  production-database test.

## Day-by-day status

| Day | Current status | Evidence / remaining acceptance |
|---:|---|---|
| 1 | Implemented and tested | Async backend, schemas and bounded queues have repository tests. Full consuming-system sign-off is not recorded. |
| 2 | Partial operational acceptance | Ring-buffer capture was demonstrated in a controlled WSL lab. Long-run capture health and post-fix sustained behavior are not fully established. |
| 3 | Verified in tests | TCP reassembly and HTTP parser edge cases are covered. Broader real-network replay remains unverified. |
| 4 | Verified locally | Broker serialization and topic behavior are tested. PUB/SUB remains best-effort and non-durable. |
| 5 | Partial | Downstream topic contracts are tested locally. Member 3/4 consumer acceptance is still required. |
| 6 | Partial — performance gate open | A pre-fix 30-minute live run had persistence rejections. The batching change passed a 1,000-request live check; sustained-load success after the fix is not yet demonstrated. |
| 7 | Parser implementation verified; freeze pending | Chunked, multipart, query, body-limit, HEAD and interim-response cases have tests. Formal Phase 1 freeze awaits Day 5/6 closure. |
| 8 | Repository models verified | SQLite/ORM tests cover endpoints, transactions and incidents. PostgreSQL/production migration acceptance is not evidenced. |
| 9 | Verified in tests and controlled runtime | Correlation and persistence tests pass. The new batching path has focused regression coverage and short live validation. |
| 10 | Verified locally with limitations | Alert bus and post-commit publication are tested. Durable replay and authenticated frontend integration are not established. |
| 11 | API implementation verified in tests | Endpoints and OpenAPI contracts are tested. Live React dashboard integration is not confirmed. |
| 12 | Verified in tests | Sliding-window deduplication, expiry and suppression metrics are covered. |
| 13 | Partial | Canonical incident schema is tested inside this repository. Member 3/4 schema compatibility still needs confirmation. |
| 14 | Documentation/API tests verified; freeze pending | API documentation and OpenAPI tests exist. Formal Phase 2 acceptance remains outstanding. |
| 15 | Partial — queue-stability gate open | Synthetic serialization and queue tests exist. The pre-fix 30-minute run reached the 12,000-job queue capacity and rejected 36,317 jobs. Post-fix sustained behavior has not yet been proven. |
| 16 | Controlled lab verified; integrations open | BOLA capture, detection, persistence and redaction were demonstrated. Real billing-service authorization and end-to-end dashboard delivery remain unverified. The recorded 49.223 ms value is one observation, not a general guarantee. |
| 17 | Controlled WSL application-lifecycle path verified | Lab evidence records a verdict reaching the kernel map, matching traffic being dropped, unrelated traffic passing, expiry restoring traffic, and cleanup succeeding. Production readiness is not claimed. |

## Persistence saturation — chronological evidence

### Pre-batching failure

The 30-minute controlled run before the batching change reported:

- Successful HTTP responses: 658,632
- Persisted-record counter delta: 622,315
- Persistence rejections: 36,317
- Persistence failures reported by the store: 0
- Maximum persistence queue depth: 12,000
- Final measured queues: empty; capture remained running

This is a real failed persistence acceptance result and must remain in the record.

### Post-batching validation

The committed change batches eligible ordinary transactions in a shared
database transaction. Login and invoice routes that depend on BOLA detector
state remain on the individual-save path. If batch saving raises an exception,
the worker attempts individual saves.

The short post-change validation passed with 1,000 persisted records and zero
reported rejections/failures. This does **not** establish that sustained queue
saturation is resolved. A batch commit also has group-rollback semantics, so
failure recovery remains an area to validate.

Details: `PERSISTENCE_QUEUE_SATURATION_FIX_2026-10-25.md`.

## Remaining acceptance gates — prioritized

1. **External integration:** obtain explicit Member 3/4 confirmation that they
   accept the Day 5 topic payloads and Day 13 canonical incident schema.
2. **Phase decisions:** record the formal Phase 1 decision for Day 7 and Phase 2
   decision for Day 14 after their dependencies are satisfied.
3. **Persistence/load:** perform one bounded post-fix sustained validation with
   persistence-rejection, queue, packet-drop, throughput and memory evidence.
   Do not call the saturation issue resolved solely from the 1,000-request run.
4. **Day 16 integration:** obtain authoritative billing-service setup/test
   instructions and verify the intended authorized test scenario and dashboard
   delivery, if these services are part of the required acceptance scope.
5. **Update acceptance evidence and verify the remote commit** after any further
   source or documentation change.

## Scope and safety

- Application-code implementation commit: `53ad9e9` (acceptance-documentation updates: `e24031c`, `4ec76d4`).
- Local DBs, backups, compiled eBPF objects and unrelated untracked artifacts
  were not included in that commit.
- Keep Day 17 packet-drop enforcement disabled outside the isolated disposable
  lab unless the required deployment and safety controls are established.
- Do not start Day 18 until the agreed Day 1–17 acceptance gates are resolved.

## Post-batching live validation — 2026-10-26

**Result: PASS — bounded 120-second live loopback test.**

- Configured load duration: 120 seconds; concurrency: 8.
- Completed and successful HTTP requests: 39,282 / 39,282.
- Successful response rate: 327.3 requests/second.
- Latency p50/p95/p99: 23.624 / 34.456 / 42.088 ms.
- Persisted-record counter delta: 39,282.
- Persistence failures/rejections: 0 / 0.
- Packet rejections/drops: 0 / 0.
- TCP stream-limit rejections/reassembly-buffer overflows: 0 / 0.
- Final raw-packet, header, metadata, and persistence queue depths: 0.
- Capture running at test completion: true.
- RSS baseline/peak/growth: 79.0 / 86.6 / 7.6 MiB.
- Boundary: HTTP client through the loopback capture, parser, and persistence pipeline. This was not a physical-NIC or production-database benchmark.

**Interpretation:** The batching change passed this bounded workload with no observed persistence rejections or failures, complete persistence of successful requests, drained queues, and RSS growth below the configured limit.

**Remaining limitation:** The earlier 30-minute run recorded 36,317 persistence rejections before the batching change. This 120-second post-change pass does not prove that the long-duration saturation issue is resolved. Sustained post-change acceptance remains open; no claim of production readiness is made.


## Final local regression verification — 2026-10-26

- Command: `python -m pytest -q` with the project `.venv` active.
- Result: **206 passed, 1 warning in 10.05 seconds**.
- The warning is a Starlette deprecation warning related to `httpx` with
  `starlette.testclient.TestClient`; it did not cause test failures.
- The standalone `pytest -q` invocation failed collection because the
  repository package `app` was not on its import path. Running pytest as
  `python -m pytest` resolved the invocation issue without application-code
  changes.
- After the bounded live validation, the API, ring reader, and Day 16 producer
  were stopped; the pinned event map was removed and the loopback ingress
  filter was verified empty.
