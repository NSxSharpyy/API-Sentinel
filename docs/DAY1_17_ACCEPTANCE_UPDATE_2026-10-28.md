# API-Sentinel — Day 1–17 Acceptance Update

Audit date: 2026-10-28
Branch: backend-parser
Requirements source: Backend_Parsing.pdf

## 1. Executive decision

**Day 1–17 acceptance remains open.**

The earlier sustained-ingestion workload failed persistence acceptance, with
9,182 persistence rejections. After the async bulk-insert change, two subsequent
60-second live loopback soak tests passed at concurrency 8 and 12. Every
successful HTTP request in those runs was persisted, with zero packet drops,
persistence failures, or persistence rejections.

These later runs are positive evidence for the tested WSL loopback workload.
They do not prove production readiness, physical-NIC line rate, long-duration
stability, or the separate Day 15 sub-millisecond serialization target.

This update supplements, rather than replaces, historical evidence. Day 6
controlled-loopback results are now passing at the two tested concurrency
levels; broader sustained acceptance remains open. Day 15 remains open pending
its separate timing and queue-stability evidence.

## 2. Latest local verification

Recorded terminal evidence on 2026-10-28:

- Python compilation: passed.
- Focused tests after the bulk-insert patch: 26 passed, 1 existing warning.
- Full pytest suite after the bulk-insert patch: 250 passed, 1 existing warning.
- `git diff --check`: passed.
- The warning is an existing Starlette deprecation warning involving `httpx`
  and `starlette.testclient.TestClient`.

The previously committed instrumentation/report update `7cba105` passed GitHub
Actions Python tests, run
[40690053691](https://github.com/NSxSharpyy/API-Sentinel/actions/runs/40690053691).
The subsequent report update `047534d` was also pushed and passed Python tests,
run
[40691896139](https://github.com/NSxSharpyy/API-Sentinel/actions/runs/40691896139).

The bulk-insert change and its tests are currently an uncommitted local patch.
Those changes do not yet have a GitHub Actions result; do not imply otherwise.

## 3. Latest sustained-ingestion evidence

Test boundary: HTTP client -> loopback capture -> parser -> persistence.
These are WSL loopback tests, not physical-NIC or production-database benchmarks.

### Earlier failed workload — retained as historical evidence

Before the bulk-insert patch, an earlier 60-second run at concurrency 8 with
batch maximum 64 used:

`~/api-sentinel-diagnostics/day615-stage-timing-20261028/api-sentinel-stage-timing.sqlite`

- Successful HTTP requests: 24,255.
- Successful response rate: 404.0 requests/second.
- HTTP p50 / p95 / p99: 19.216 / 25.610 / 31.214 ms.
- Accepted packets / accepted TCP events: 291,812 / 291,812.
- Persisted transactions: 15,073.
- Persistence rejections: 9,182; reported store failures: 0.
- Packet drops: 0; the bounded persistence queue reached 12,000.
- All queues eventually drained and capture remained running.
- RSS growth: 37.9 MiB.

This run failed persistence acceptance: 15,073 persisted plus 9,182 rejected
equals 24,255 successful HTTP responses. Draining the queue later did not recover
the jobs rejected during admission.

### Later live run — concurrency 8

After the async bulk-insert patch, FastAPI used the fresh diagnostic database:

`~/api-sentinel-diagnostics/day615-live-20261028-131513/live.sqlite3`

The actual async application connection was verified to use SQLite WAL mode and
`synchronous=FULL`. Batch maximum was 64. Load duration was 60 seconds.

- Completed / successful HTTP requests: 46,812 / 46,812.
- Successful response rate: 780.0 requests/second.
- HTTP p50 / p95 / p99: 9.969 / 12.429 / 13.530 ms.
- Accepted packets / accepted TCP events: 561,768 / 561,768.
- Persisted transactions: 46,812.
- Persistence failures / rejections: 0 / 0.
- Packet drops, stream-limit rejections, and reassembly-buffer overflows: 0.
- Final raw-packet, header, metadata and persistence queues: all zero.
- Capture remained running at completion.
- RSS baseline / sampled peak / growth: 81.1 / 87.9 / 6.8 MiB.
- Result: `LIVE CAPTURE SOAK TEST: PASS`.

### Later live run — concurrency 12

The same running application and diagnostic database were tested at concurrency
12 for a further 60 seconds.

- Completed / successful HTTP requests: 44,863 / 44,863.
- Successful response rate: 747.4 requests/second.
- HTTP p50 / p95 / p99: 14.985 / 19.894 / 35.665 ms.
- Accepted packets / accepted TCP events: 538,372 / 538,372.
- Persisted transactions: 44,863.
- Persistence failures / rejections: 0 / 0.
- Packet drops, stream-limit rejections, and reassembly-buffer overflows: 0.
- Final raw-packet, header, metadata and persistence queues: all zero.
- Capture remained running at completion.
- RSS baseline / sampled peak / growth: 87.9 / 105.1 / 17.2 MiB.
- Result: `LIVE CAPTURE SOAK TEST: PASS`.

### Interpretation and remaining limitations

The two later tests passed all reported soak-test criteria at the tested
concurrency levels. The concurrency-8 run had higher observed throughput and
lower latency than the concurrency-12 run; increasing concurrency did not
improve throughput in this comparison.

These are two bounded runs, not proof of indefinite stability. The earlier
failed run is useful historical evidence, but the runs used different diagnostic
databases and are not a fully controlled before/after experiment. Do not
attribute the entire performance difference solely to the bulk-insert change.

The latest soak-test output did not establish the Day 15 sub-millisecond
serialization target or report a new queue-wait p95. Keep that acceptance gate
open. The `session.commit()` timing also includes SQLAlchemy pending-write work;
it must not be described as disk-flush time alone.

## 4. Updated acceptance matrix

| Day | Status as of 2026-10-28 | Evidence or remaining gate |
|---:|---|---|
| 1 | Locally verified; external sign-off open | Schemas, bounded queues and backend tests exist. Full consuming-system acceptance is not recorded. |
| 2 | Partial | Controlled ring-buffer capture was demonstrated. Sustained capture health and overflow behavior remain open. |
| 3 | Verified in automated tests | TCP/HTTP reassembly tests exist. Broader real-network replay remains unverified. |
| 4 | Verified locally with limitations | Broker/topic tests exist. PUB/SUB remains best-effort and non-durable. |
| 5 | Partial; external blocker | Member 3/4 must accept the exact downstream topics and payload contract. |
| 6 | **Controlled loopback soak passed; broader acceptance open** | Two post-change 60-second runs at concurrency 8 and 12 persisted every successful request with zero reported drops, persistence failures, or rejections. Longer-duration stability and broader deployment acceptance remain open. |
| 7 | Implementation verified; Phase 1 freeze pending | Formal decision depends on Day 5/6 acceptance and review. |
| 8 | Repository-local models verified | Production database migration and PostgreSQL acceptance are not evidenced. |
| 9 | Verified in tests and controlled runtime | Correlation and persistence tests exist; sustained persistence acceptance remains separate. |
| 10 | Verified locally with limitations | Alert delivery is bounded, in-process, best-effort and non-durable. |
| 11 | API/OpenAPI verified locally | Live React dashboard integration is not confirmed. |
| 12 | Verified in automated tests | Deduplication behavior is tested; persisted incidents are not suppressed by notification deduplication. |
| 13 | Partial; external blocker | Member 3/4 compatibility with the canonical incident schema is not confirmed. |
| 14 | Documentation/API verified; Phase 2 freeze pending | Formal Phase 2 decision and external review remain outstanding. |
| 15 | **Not accepted; timing gate open** | The earlier run reached queue capacity and rejected jobs. The two later runs drained without reported rejections, but the separate sub-millisecond serialization target and fresh queue-wait p95 evidence have not been established. |
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
5. **Days 6/15:** The bulk-insert patch has two passing 60-second loopback
   soak runs at concurrency 8 and 12. Preserve the earlier failed run in the
   evidence record. Do not claim a controlled causal improvement from these
   non-identical workloads. Day 15 still needs its dedicated sub-millisecond
   serialization measurement and queue-stability evidence.

## 6. Git and evidence integrity

The branch is `backend-parser`. Before this pending patch, commit `047534d`
(`Update acceptance report with CI result`) was pushed to `origin/backend-parser`
and remote synchronization was verified. Its GitHub Actions Python tests run
`40691896139` passed.

The current uncommitted patch contains these source/test changes:

- `app/async_transaction_store.py`
- `app/main.py`
- `tests/test_async_transaction_store.py`
- `tests/test_day1.py`

This report is the fifth intended tracked change. The patch adds SQLAlchemy bulk
insertion for ordinary batched transaction rows and exposes insertion-duration
metrics. BOLA-sensitive transactions still take the individual persistence
path. The full local suite passed after these source changes, but this patch
does not yet have a commit or CI result.

Untracked local databases, backups, the live benchmark script, eBPF loaders and
objects, and other local artifacts were present during the audit. They must be
preserved and must not be staged as part of this change. In particular, do not
use `git add .`.

## 7. Final disposition

- Local compilation and automated regression suite: **PASS** (250 tests; one
  existing warning).
- Earlier 60-second sustained-ingestion workload: **FAIL** (9,182 persistence
  rejections); retained as historical evidence.
- Later 60-second live capture run, concurrency 8: **PASS**.
- Later 60-second live capture run, concurrency 12: **PASS**.
- Day 6 controlled WSL loopback evidence: **PASS at the two tested concurrency
  levels; broader acceptance remains open**.
- Day 15 sub-millisecond serialization and queue-stability acceptance: **OPEN**.
- External integration and formal phase decisions: **OPEN**.
- GitHub Actions for base commit `047534d`: **VERIFIED PASS** (run `40691896139`).
- Current bulk-insert patch: local tests passed; **commit and CI verification
  still pending**.

Do not start Day 18 until the Day 1–17 acceptance gates are resolved or all
remaining external blockers are explicitly documented.
