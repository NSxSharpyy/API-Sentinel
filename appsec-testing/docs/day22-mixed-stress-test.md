# Day 22 — Mixed-Traffic Stress Test

## 1. Objective and scope

Exercise legitimate billing requests concurrently with adversarial cross-customer
invoice requests. Record workload outcomes, latency probes, container resource
samples, and enforcement-adapter activity.

This runner uses the Day 21 HTTP enforcement adapter through the Day 20
fail-open wrapper. It is an **application-layer simulation**, not proof of
TC/eBPF packet drops or kernel-level enforcement.

The Day 19 TC/eBPF experiment is a separate integration path. Its classifier is
not an HTTP proxy and cannot be substituted directly for the Day 21 adapter
at port 8004.

## 2. Prerequisites

Run commands from the `appsec-testing` directory in the recovery repository.

Before running the workload:

1. Confirm auth, user, order, and billing services are healthy on ports
   5001–5004.
2. Confirm the seeded customer and invoice data is available.
3. Ensure ports 8004 and 8005 are free.
4. Ensure the Docker-compatible CLI can run `docker stats --no-stream`.
5. Review the local-lab scope and make sure the workload will not reach
   production systems.

The runner starts its own Day 21 adapter on port 8004 and Day 20 wrapper on
port 8005. The wrapper is explicitly configured through `DAY20_ENFORCER_URL`,
`DAY20_DIRECT_UPSTREAM_URL`, and `DAY20_WRAPPER_PORT`. The runner terminates
the child processes it starts during cleanup.

Do not run `docker compose down -v`, volume-pruning commands, or commands that
delete existing database volumes.

## 3. Normal acceptance workload

Run:

```bash
python scripts/enforcement/mixed_stress_test.py
```

The default workload plans 2,000 requests:

- 1,800 legitimate requests (90%)
- 200 adversarial requests (10%)
- 15 legitimate workers
- 5 adversarial workers

The runner uses separate worker pools so the configured worker counts control
the concurrency of each traffic class.

Default report: `logs/mixed_stress_report.json`

### Acceptance criteria

The report must satisfy all of the following:

- Exactly 2,000 observed workload requests.
- Exactly 1,800 legitimate and 200 adversarial requests.
- Legitimate traffic ratio between 85% and 95%, inclusive.
- Legitimate success rate of at least 98%.
- Adversarial enforcement block rate of at least 30%.
- At least one latency probe and zero failed latency probes.
- At least one resource sample and zero resource-sampling errors.
- Enforcement-adapter activity observed.

Only HTTP 403 responses with `X-Day21-Enforcement: blocked` count as
enforcement blocks. HTTP 404 responses and ordinary request errors do not
count as blocks. Legitimate success means an HTTP 2xx or 3xx response.

Inspect the JSON report's counts, metrics, checks, errors, and evidence-type
fields; do not rely only on the process exit code.

## 4. Continuous latency and resource sampling

### Latency

The runner records timestamped latency-probe results and failures. The report
includes minimum, p50, median, p95, and maximum observed latency, plus the
probe timeline. These measurements describe this local run and are not
production performance guarantees.

### Container resources

Approximately every two seconds, the runner invokes `docker stats --no-stream`
and records timestamped container CPU percentage, memory usage in MB, and
memory limit in MB.

The report includes:

- `resource_samples`: timestamped per-container samples.
- `resource_sampling_errors`: command or parsing errors.
- `resource_summary.container_peaks`: maximum sampled CPU and memory values
  for each container.
- `resource_summary.max_cpu_percent_across_containers` and
  `resource_summary.max_memory_used_mb_across_containers`: highest per-container
  observed peaks.

These are peaks observed at the sampling intervals, not continuous telemetry;
short-lived spikes between samples may not be captured.

## 5. Negative live workload

Use a separate report path so the negative test does not overwrite the normal
acceptance evidence:

```bash
python scripts/enforcement/mixed_stress_test.py \
  --total-requests 1000 \
  --legit-ratio 0.50 \
  --legit-workers 3 \
  --adversarial-workers 20 \
  --report logs/mixed_stress_negative_report.json
```

This intentionally plans 500 legitimate and 500 adversarial requests. The
request counts can be correct while the run fails acceptance because a 50%
legitimate ratio is outside the permitted 85–95% range. A nonzero exit code
and `overall: FAIL` are expected for this negative scenario. Check the report
to confirm the ratio guard failed and inspect all other checks independently.

The unit-level negative-ratio regression test can be run without live traffic:

```bash
python -m pytest -q tests/test_day22_mixed_stress.py
```

## 6. Exploratory workload

After reviewing the acceptance run, execute the larger exploratory workload:

```bash
python scripts/enforcement/mixed_stress_test.py \
  --exploratory \
  --total-requests 6000 \
  --legit-workers 40 \
  --adversarial-workers 10
```

With the default 90% ratio, this plans 5,400 legitimate and 600 adversarial
requests.

Report: `logs/mixed_stress_exploratory_report.json`

This is an exploratory stress run, not a replacement for the 2,000-request
acceptance result. Review its completion checks, sampling errors, latency
failures, and workload errors.

## 7. Evidence and limitations

Reports include planned and observed counts, request outcomes, traffic ratios,
latency probes, resource samples and summaries, adapter statistics, checks,
and errors.

A passing run demonstrates only behavior observed in this local
application-layer simulation. It does not prove kernel packet drops, prove
the real TC/eBPF fail-open behavior, or establish production capacity.
