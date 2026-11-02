# Day 27 — Sustained Endurance Stress Test

## Objective

Run the Day4 legitimate traffic generator continuously for six hours while
sampling API-Sentinel service health and resource usage.

The test records:

- Request totals, failures, and HTTP/transport error rate.
- Cumulative request latency percentiles (p50, p95, and p99).
- CPU utilization and memory usage for auth, user, order, and billing.
- Application database file size.
- Resource-usage and database-size trends per hour.
- Sampling errors and generator exit status.

This test measures sustained lab behavior. It does not independently prove
kernel-level blocking or establish production reliability.

## Implementation

- Runner: `scripts/stress/endurance_test.py`
- Tests: `tests/test_day27_endurance.py`
- Default output directory: `logs/day27/`
- Default checkpoint file: `logs/day27/endurance_checkpoints.jsonl`
- Default report: `logs/day27/endurance_report.json`

The runner uses the Day4 traffic generator and samples the auth, user,
order, and billing containers. It also samples the application database
file used by the order service.

## Prerequisites

Run all commands from the `appsec-testing` directory.

1. Docker and Docker Compose must be available.
2. API-Sentinel services must be running and healthy.
3. The Day4 traffic generator must exist at
   `scripts/traffic/traffic_generator.py`.
4. Required Python dependencies must be installed.
5. Ensure sufficient disk space for logs and checkpoints.
6. Keep the machine running and prevent sleep during the test.

Check service health:

```bash
python scripts/check_health.py
```

## Test Execution

The six-hour endurance test was executed with:

```bash
python scripts/stress/endurance_test.py \
  --hours 6 \
  --sample-interval 60 \
  --concurrency 10 \
  --seed 27 \
  --output-dir logs/day27/run_6h_final_attempt3
```

Original evidence:

- Report: `logs/day27/run_6h_final_attempt3/endurance_report.json`
- Checkpoints: `logs/day27/run_6h_final_attempt3/endurance_checkpoints.jsonl`

No additional six-hour run is required. The following results are taken
from the original completed report.

## Official Six-Hour Result

**Status: COMPLETED**

| Metric | Result |
|---|---:|
| Target duration | 21,600 seconds |
| Observed duration | 21,602.5 seconds |
| Total requests | 1,319,549 |
| Failed requests | 0 |
| Error rate | 0.0% |
| p50 latency | 3.73 ms |
| p95 latency | 119.41 ms |
| p99 latency | 172.16 ms |
| Latency samples | 1,319,549 |
| Checkpoints | 363 |
| Samples | 361 |
| Sampling errors | 0 |
| Malformed log lines | 0 |
| Generator exit code | 0 |
| Interrupted | false |

The database size remained 81,920 bytes between the first and last samples.

The report records `status: COMPLETED` and
`evidence_type: legitimate_traffic_endurance`. The observed duration
exceeded the six-hour target, so the Day27 lab endurance objective was met.

### Container Memory Trends

| Service | Memory trend |
|---|---:|
| Auth | +0.938 MiB/hour |
| User | +0.055 MiB/hour |
| Order | +0.523 MiB/hour |
| Billing | -0.093 MiB/hour |

These are descriptive trends, not pass/fail thresholds or proof of the
absence or presence of a memory leak.

## Supplementary Five-Minute Smoke Test

A separate five-minute run was completed as supplementary validation.
It does not replace the official six-hour result.

Execution:

```bash
python scripts/stress/endurance_test.py \
  --hours 0.0833 \
  --sample-interval 30 \
  --concurrency 10 \
  --seed 27 \
  --output-dir logs/day27/short_run_5m
```

Evidence:

- Report: `logs/day27/short_run_5m/endurance_report.json`
- Checkpoints: `logs/day27/short_run_5m/endurance_checkpoints.jsonl`

| Metric | Result |
|---|---:|
| Status | COMPLETED |
| Observed duration | 300.95 seconds |
| Total requests | 18,760 |
| Failed requests | 0 |
| Error rate | 0.0% |
| p50 latency | 2.91 ms |
| p95 latency | 97.96 ms |
| p99 latency | 122.6 ms |
| Checkpoints | 13 |
| Samples | 11 |
| Sampling errors | 0 |
| Generator exit code | 0 |
| Interrupted | false |

This short run is supplementary smoke-test evidence only.

## Report Interpretation

- `COMPLETED`: the configured duration was reached and the generator
  completed successfully.
- `COMPLETED_WITH_WARNINGS`: the run completed but recorded warnings.
- `INTERRUPTED`: the run stopped before its planned completion.
- `INCOMPLETE` or `RECOVERED_PARTIAL`: the available evidence does not
  establish a completed six-hour run.

Review duration, request metrics, sampling errors, generator exit code,
and interruption status together. A partial recovery report must not be
presented as a six-hour completion certificate.

## Validation

Run the focused Day27 tests:

```bash
python -m pytest -q tests/test_day27_endurance.py
```

Run the full application-security test suite:

```bash
python -m pytest -q tests
```

## Scope and Limitations

This test measures sustained legitimate-traffic behavior in the
API-Sentinel lab environment. It records request outcomes, latency,
container resource observations, database size, and sampling quality.

It does not certify production readiness, prove kernel-level packet drops,
or establish adversarial traffic enforcement effectiveness. Those claims
require separate evidence.
