# API-Sentinel Days 1–17: Acceptance Evidence Update

Date: 2026-10-25
Branch: `backend-parser`
Baseline commit: `0a0aef5` — `Improve persistence throughput and benchmark metrics`

## Automated tests and source checks

After changing the persistence queue capacity from 2,500 to 12,000:

- Full test suite: **202 passed**, one existing Starlette deprecation warning.
- `git diff --check`: passed.
- Runtime confirmed persistence queue capacity of 12,000.
- Raw-packet queue metrics are exposed by the live API; the raw queue capacity is 10,000.

## Live loopback benchmark results

All runs used the real local capture-to-persistence path. These are WSL loopback results, not physical-NIC line-rate measurements or production-database benchmarks.

| Requests | Concurrency | Throughput (req/s) | P50 (ms) | P95 (ms) | P99 (ms) | Persisted | Persistence rejected | Packet rejected/dropped | RSS growth (MiB) | Result |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 500 | 8 | 210.7 | 34.209 | 59.188 | 75.922 | 500 | 0 | 0 / 0 | 2.9 | PASS |
| 1,000 | 16 | 251.1 | 61.073 | 99.985 | 124.020 | 1,000 | 0 | 0 / 0 | 2.5 | PASS |
| 2,000 | 32 | 279.6 | 109.012 | 173.175 | 218.560 | 2,000 | 0 | 0 / 0 | 0.6 | PASS |
| 5,000 | 32 | 272.6 | 114.830 | 172.463 | 217.152 | 5,000 | 0 | 0 / 0 | 2.7 | PASS |
| 10,000 | 32 | 281.0 | 110.353 | 168.352 | 207.960 | 8,220 | 1,780 | 0 / 0 | 3.2 | FAIL — queue capacity 2,500; 20-second drain |
| 10,000 | 32 | 286.6 | 106.296 | 176.292 | 212.182 | 10,000 | 0 | 0 / 0 | 16.8 | PASS — queue capacity 12,000; 60-second drain |

For the final 10,000-request run:

- 10,000 HTTP requests succeeded.
- 10,000 transactions were persisted within the 60-second drain window.
- Packet rejected/dropped, TCP stream-limit rejection, reassembly overflow, persistence failure, and persistence rejection deltas were all zero.
- Raw and persistence queues drained to zero; capture remained running.
- RSS growth was 16.8 MiB, within the benchmark's configured 128 MiB limit.

The earlier 10,000-request failure is retained as evidence: the 2,500-item persistence queue rejected 1,780 transactions. Increasing the bounded queue to 12,000 allowed the tested burst to drain without rejections. This demonstrates burst handling for this workload; it does not prove unlimited or long-duration capacity.

## Remaining acceptance items

1. **Day 5 and Day 13:** obtain Member 3/4 consumer contract and compatibility acceptance.
2. **Day 7 and Day 14:** record formal Phase 1 and Phase 2 freeze decisions.
3. **Days 6 and 15:** controlled loopback workloads passed at the sizes above, but this is not a long-duration stability test. Production-database behavior also remains unverified.
4. **Day 17:** the controlled WSL application-lifecycle enforcement test is recorded as passed in `docs/DAY17_POLICY_INTEGRATION.md`. Keep enforcement opt-in and lab-scoped; this result does not establish production readiness or sustained detection-to-enforcement latency.
5. Confirm CI status for the latest pushed commit `4f2cdc0`; local tests passed and the local/remote commit hashes matched. Do not stage local database files, backups, compiled artifacts, or unrelated untracked files.

## Overall status

The local tests and final controlled 10,000-request loopback benchmark pass with the updated queue capacity. **Do not mark all Days 1–17 complete yet:** the external acceptance decisions and remaining scope limits above still need to be resolved.


## Day 16 BOLA validation update — 2026-10-25

**Status: PARTIALLY VERIFIED**, based on the project team's response.

- `tests/test_bola_detection.py`: 7 passed.
- Combined BOLA, transaction-store, alert-bus and API tests: 25 passed,
  with one existing Starlette deprecation warning.
- Existing controlled-lab documentation records one capture-to-detection
  latency measurement of 49.223 ms. This is one observation, not a percentile
  or a general latency guarantee.
- A repository search did not identify a separate billing-service
  implementation or dedicated billing simulation script.
- Real billing endpoint authorization has not been tested in this validation.
  The authoritative billing-service repository, local setup, authorized
  test-account instructions and dashboard location have not yet been provided.
- Full live billing-service-to-dashboard delivery remains pending confirmation.
  The project team said it would check for the authoritative details.

No claim is made that a real billing endpoint was exploited or that its
authorization behavior has been verified.
