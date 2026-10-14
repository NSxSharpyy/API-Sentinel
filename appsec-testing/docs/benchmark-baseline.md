# API-Sentinel: Baseline Latency Benchmark

## 1. Objective

Establish a repeatable performance baseline for the mock e-commerce API services before adding API security monitoring.

## 2. Services Tested

| Service | URL |
|---|---|
| Authentication | http://127.0.0.1:5001 |
| User | http://127.0.0.1:5002 |
| Orders | http://127.0.0.1:5003 |
| Billing | http://127.0.0.1:5004 |

The workload performs login, token verification, profile retrieval, order listing, invoice listing, and retrieval of an invoice belonging to the authenticated customer.

## 3. Prerequisites

- API services are running and healthy.
- k6 is installed.
- The synthetic test database is seeded.
- Test account credentials are valid.

## 4. Running the Benchmark

From the repository root:

    cd ~/API-Sentinel
    bash ./appsec-testing/benchmarks/run_benchmark.sh

To configure the workload:

    VUS=2 DURATION=30s bash ./appsec-testing/benchmarks/run_benchmark.sh

Short validation run:

    VUS=2 DURATION=5s bash ./appsec-testing/benchmarks/run_benchmark.sh

The runner checks service health, executes k6, exports JSON results, and saves a console log.

## 5. Configuration

Benchmark script: `appsec-testing/benchmarks/baseline.js`

| Variable | Default | Purpose |
|---|---|---|
| API_BASE_URL | http://127.0.0.1 | Base host used by the runner |
| AUTH_URL | http://127.0.0.1:5001 | Authentication service URL |
| USER_URL | http://127.0.0.1:5002 | User service URL |
| ORDER_URL | http://127.0.0.1:5003 | Order service URL |
| BILLING_URL | http://127.0.0.1:5004 | Billing service URL |
| DEMO_PASSWORD | Password123! | Synthetic test account password |
| USERNAMES | Exported from seeded database | Customer accounts used by the runner |
| DB_PATH | data/shop.db under the repository root | SQLite database used to export usernames |
| VUS | 10 | Number of virtual users |
| DURATION | 30s | Test duration |

Use only synthetic test credentials. Never commit real passwords or tokens.

## 6. Initial 30-Second Baseline

Recorded on 2026-10-14.

| Metric | Result |
|---|---:|
| Throughput | 130.485 requests/sec |
| HTTP requests | 3,918 |
| Average latency | 14.814 ms |
| Median latency | 2.396 ms |
| P90 latency | 72.487 ms |
| P95 latency | 75.761 ms |
| Maximum latency | 217.529 ms |
| Failed request rate | 0% |
| Check pass rate | 100% |

JSON result: `baseline_20261014_063005.json`

Console log: `console_20261014_063005.log`

Both files are under `appsec-testing/benchmarks/results/`.

## 7. Short Validation Run

Recorded on 2026-10-14.

| Metric | Result |
|---|---:|
| Throughput | 128.301 requests/sec |
| HTTP requests | 648 |
| Average latency | 15.016 ms |
| Median latency | 2.575 ms |
| P90 latency | 73.997 ms |
| P95 latency | 78.042 ms |
| Maximum latency | 95.521 ms |
| Failed request rate | 0% |
| Check pass rate | 100% |

JSON result: `baseline_20261014_064139.json`

Console log: `console_20261014_064139.log`

Both files are under `appsec-testing/benchmarks/results/`.

The short run validates the runner; use the longer run as the initial baseline.

## 8. Latest Short Validation Run

Recorded on 2026-10-14 using 2 virtual users for 5 seconds.

| Metric | Result |
|---|---:|
| Throughput | 20.003 requests/sec |
| HTTP requests | 108 |
| Completed iterations | 18 |
| Average latency | 15.984 ms |
| Median latency | 2.617 ms |
| P90 latency | 80.562 ms |
| P95 latency | 83.251 ms |
| P99 latency | 89.996 ms |
| Maximum latency | 90.783 ms |
| Failed request rate | 0% |
| Check pass rate | 100% |

Per-endpoint latency samples: 18 each for login, verification, profile, orders, and invoices.

JSON result: `baseline_20261014_072348.json`

Console log: `console_20261014_072348.log`

Both files are under `appsec-testing/benchmarks/results/`. The console log records all four configured thresholds as passed. Use the console log as the threshold evidence for this run because the exported JSON threshold flags appear inconsistent with the console output.

## 9. Official 10-VU Baseline Run

Recorded on 2026-10-14 using 10 virtual users for 30 seconds.
The run completed, but **failed the required P95 latency threshold**.

| Metric | Result |
|---|---:|
| Virtual users | 10 |
| Duration | 30s |
| HTTP requests | 2,838 |
| Completed iterations | 473 |
| Throughput | 93.050 requests/sec |
| Average request latency | 22.595 ms |
| Median request latency (P50) | 3.337 ms |
| P90 latency | 87.096 ms |
| P95 latency | 117.511 ms |
| P99 latency | 219.393 ms |
| Maximum latency | 477.432 ms |
| Failed HTTP request rate | 0% |
| Check pass rate | 100% (3,311/3,311) |
| P95 threshold (<50 ms) | **FAILED** |

Per-endpoint latency:
- Login: average 115.889 ms; P95 231.775 ms.
- Token verification: average 4.204 ms; P95 12.028 ms.
- Profile: average 3.765 ms; P95 8.516 ms.
- Orders: average 4.052 ms; P95 10.380 ms.
- Invoice detail: average 3.667 ms; P95 8.801 ms.

JSON result: `baseline_20261014_083000.json`

Console log: `console_20261014_083000.log`

Both files are under `appsec-testing/benchmarks/results/`.

The k6 console reported P95 = 117.51 ms against the required `p(95)<50`
threshold and exited with status 99. The HTTP failure rate was 0% and all
checks passed. The run is therefore a completed measurement, but it does
not pass the latency requirement.

The exported JSON contains threshold metadata inconsistent with the console
and raw metric values. Preserve both artifacts; investigate the discrepancy
before relying on JSON threshold flags. The console output is the recorded
evidence for this run's threshold outcome.

Login latency is the main observed hotspot in this run. Investigate it before
making performance changes; do not weaken the 50 ms requirement to make the
benchmark appear to pass.

The runner states that the eBPF sidecar must be absent, but this run's output
alone does not independently prove that state. Verify the running stack before
using this as definitive no-sidecar evidence for the Day 15 comparison.

## 10. Thresholds

- HTTP request failure rate below 1%.
- Custom benchmark error rate below 1%.
- API check pass rate above 99%.
- HTTP request P95 latency below 50 ms (`p(95)<50`).

A run that exceeds the P95 threshold is a measured run, not a passing
baseline validation. Do not silently relax this threshold.

Passing these thresholds indicates that the tested workload met its configured checks. It does not prove that the API is free of security vulnerabilities.

## 11. Metric Interpretation

- Throughput: HTTP requests processed per second.
- Average and median latency: typical response times.
- P90 and P95 latency: response-time percentiles.
- Maximum latency: slowest observed request.
- Failed request rate: proportion of failed HTTP requests.
- Check pass rate: proportion of successful k6 checks.

## 12. Repeatable Comparisons

Keep virtual users, duration, test data, service configuration, host resources, and network conditions as consistent as possible between runs.

Compare throughput, P95 latency, average latency, failure rate, and check pass rate before and after adding monitoring controls.

## 13. Limitations

This is a local synthetic benchmark. Results depend on the host machine, container runtime, service state, test data, and workload. These measurements are not production capacity estimates.

This baseline does not measure eBPF monitoring overhead; that requires a separate comparison with monitoring enabled and disabled.
