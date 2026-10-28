# API-Sentinel — Day 1–17 Acceptance Update

Audit date: 2026-10-28
Branch: backend-parser
Requirements source: Backend_Parsing.pdf

## 1. Executive decision

**Day 1–17 acceptance remains open.**

The latest local regression suite passes, but the latest live-capture persistence
workload fails its acceptance criteria. Automated test success does not establish
sustained operational acceptance.

This update supplements, rather than replaces, the historical acceptance
reports. Earlier successful controlled tests remain valid evidence for their
specific workloads, but they do not override the latest failed workload.

## 2. Latest local verification

Recorded terminal evidence on 2026-10-28:

- Python compilation: exit code 0.
- Full pytest suite: 250 passed, 1 warning, exit code 0.
- `git diff --check`: exit code 0.
- The warning is an existing Starlette deprecation warning involving
  `httpx` and `starlette.testclient.TestClient`.

These results apply to the local working tree at the time of that run.
The six modified tracked files have not been shown to be committed or pushed.
No GitHub Actions result for these latest uncommitted changes is established.

## 3. Latest sustained-ingestion evidence

Test boundary: HTTP client -> loopback capture -> parser -> persistence.
This is not a physical-NIC or production-database benchmark.

Configuration and workload:

- Load duration: 60 seconds.
- Concurrency: 8.
- Persistence batch maximum: 64.
- SQLite diagnostic database:
  `~/api-sentinel-diagnostics/day615-stage-timing-20261028/api-sentinel-stage-timing.sqlite`
- The measured persistence queue reached 12,000 jobs. The source and project
  documentation specify 12,000 as the default capacity; no explicit queue
  override was found in the inspected project configuration/history.

Results:

- Completed and successful HTTP requests: 24,255 / 24,255.
- Successful response rate: 404.0 requests/second.
- HTTP p50 / p95 / p99: 19.216 / 25.610 / 31.214 ms.
- Accepted packets and accepted TCP events: 291,812 / 291,812.
- Rejected packets / dropped packets: 0 / 0.
- TCP stream-limit rejections / reassembly-buffer overflows: 0 / 0.
- Persisted transactions: 15,073.
- Persistence rejections: 9,182.
- Reported persistence-store failures: 0.
- Final raw-packet, header, metadata and persistence queues: all zero.
- Capture remained running at test completion.
- RSS baseline / sampled peak / growth: 80.8 / 118.7 / 37.9 MiB.
- Persistence batch attempts / successful batch calls: 237 / 237.
- Average batch size: approximately 63.60; maximum batch size: 64.

The persisted and rejected counts reconcile with the successful HTTP count:
15,073 + 9,182 = 24,255.

The saved timing samples directly show the persistence queue reaching 12,000
jobs while the rejection counter increased. The queue subsequently drained,
but this does not recover transactions rejected during admission.

### Interpretation

**This workload fails persistence acceptance.** Transactions were rejected
when the bounded persistence queue was full, despite successful HTTP responses
and no reported store exceptions.

Batch size 64 has not demonstrated sustained acceptance. The historical
batch-size-32 baseline also failed, reporting 11,564 rejections. The original
baseline's raw benchmark files are unavailable, and these runs are not a
controlled apples-to-apples experiment. Do not claim a proven performance
improvement from the difference between their rejection counts.

No precise database-commit root cause has been established. The recorded
`session.commit()` timing includes SQLAlchemy's pending-write work and must not
be interpreted as disk-flush time alone.

## 4. Updated acceptance matrix

| Day | Status as of 2026-10-28 | Evidence or remaining gate |
|---:|---|---|
| 1 | Locally verified; external sign-off open | Schemas, bounded queues and backend tests exist. Full consuming-system acceptance is not recorded. |
| 2 | Partial | Controlled ring-buffer capture was demonstrated. Sustained capture health and overflow behavior remain open. |
| 3 | Verified in automated tests | TCP/HTTP reassembly tests exist. Broader real-network replay remains unverified. |
| 4 | Verified locally with limitations | Broker/topic tests exist. PUB/SUB remains best-effort and non-durable. |
| 5 | Partial; external blocker | Member 3/4 must accept the exact downstream topics and payload contract. |
| 6 | **Not accepted; performance gate open** | Latest 60-second live-capture test rejected 9,182 persistence jobs. |
| 7 | Implementation verified; Phase 1 freeze pending | Formal decision depends on Day 5/6 acceptance and review. |
| 8 | Repository-local models verified | Production database migration and PostgreSQL acceptance are not evidenced. |
| 9 | Verified in tests and controlled runtime | Correlation and persistence tests exist; sustained persistence acceptance remains separate. |
| 10 | Verified locally with limitations | Alert delivery is bounded, in-process, best-effort and non-durable. |
| 11 | API/OpenAPI verified locally | Live React dashboard integration is not confirmed. |
| 12 | Verified in automated tests | Deduplication behavior is tested; persisted incidents are not suppressed by notification deduplication. |
| 13 | Partial; external blocker | Member 3/4 compatibility with the canonical incident schema is not confirmed. |
| 14 | Documentation/API verified; Phase 2 freeze pending | Formal Phase 2 decision and external review remain outstanding. |
| 15 | **Not accepted; queue-stability gate open** | Queue reached 12,000 jobs; p95 queue wait was approximately 48 seconds and persistence rejections occurred. |
| 16 | Controlled lab verified; integrations open | Real billing-service authorization and full dashboard delivery remain unverified. |
| 17 | Controlled WSL lifecycle test verified historically | Production readiness and sustained detection-to-enforcement latency are not established. The lab need not be rebuilt without a specific reason. |

## 5. External blockers and requested decisions

1. **Members 3/4:** Confirm acceptance of `discovery.http.transaction`,
   `heuristics.http.transaction`, their payload contracts and the canonical
   incident schema.
2. **Phase 1:** Record the formal Day 7 freeze decision after its dependencies
   and acceptance criteria are satisfied.
3. **Phase 2:** Record the formal Day 14 freeze decision after cross-module
   compatibility and review are satisfied.
4. **Day 16 integration:** Obtain the authoritative billing-service repository,
   setup procedure, authorized test-account instructions and dashboard
   location if these integrations remain in scope.
5. **Days 6/15:** Sustained persistence acceptance remains blocked. The next
   technical change must be based on a demonstrated defect or a clear
   acceptance requirement, not speculative queue or batch-size tuning.

## 6. Git and evidence integrity

The working tree was observed on `backend-parser`, tracking `origin/backend-parser`,
with six modified tracked files:

- `app/async_transaction_store.py`
- `app/main.py`
- `app/persistence_worker.py`
- `tests/test_async_transaction_store.py`
- `tests/test_day1.py`
- `tests/test_persistence_worker.py`

Untracked databases, backups, diagnostic scripts, eBPF objects/loaders and
other local artifacts were also present. They must be preserved until their
purpose is understood.

This report does not claim that the current source changes are committed,
pushed, accepted by an external team or covered by a new GitHub Actions run.

## 7. Final disposition

- Local automated regression: **PASS**.
- Latest sustained persistence workload: **FAIL**.
- Day 6 sustained-ingestion acceptance: **OPEN**.
- Day 15 queue-stability acceptance: **OPEN**.
- External integration and formal phase decisions: **OPEN**.
- Current local Git synchronization and CI for uncommitted changes: **NOT VERIFIED**.

Do not start Day 18 until the Day 1–17 acceptance gates are resolved or all
remaining external blockers are explicitly documented.
