# Day 15 — Mid-Project Latency Milestone

## Purpose

Compare the existing Day 5 authenticated API workload against a temporary
mock-proxy path. Preserve the original `benchmarks/baseline.js` and
`benchmarks/run_benchmark.sh`.

This is a preliminary benchmark harness. It does not establish the performance
of a real eBPF sidecar.

## Components

- `benchmarks/sidecar_proxy/mock_ebpf_sidecar.py`: temporary HTTP forwarding
  proxy with a configurable artificial delay.
- `benchmarks/run_sidecar_benchmark.sh`: runs the original workload against
  the direct services and then through four mock proxies.
- `benchmarks/compute_overhead.py`: compares the selected P95 metric from two
  k6 JSON summary files.
- `tests/test_day15_overhead_calculation.py`: checks threshold behavior.

## Run

Ensure the four API services are healthy, the seeded database exists, and k6
is installed. Activate the project's virtual environment first.

```bash
python -m pytest tests/test_day15_overhead_calculation.py -q
bash benchmarks/run_sidecar_benchmark.sh 5 30s
```

The runner saves timestamped JSON summaries under `benchmarks/results/day15/`.
Use the baseline and mock-sidecar files from the same run when calculating
the delta. For example, replace the two paths below with the exact filenames
printed by the runner:

```bash
python benchmarks/compute_overhead.py \
  --baseline benchmarks/results/day15/day15_baseline_TIMESTAMP.json \
  --sidecar benchmarks/results/day15/day15_mock_sidecar_TIMESTAMP.json \
  --metric http_req_duration \
  --threshold-ms 5 \
  --out benchmarks/results/day15/overhead_report.json
```

The calculator exits with status 0 for PASS, 1 for a threshold FAIL, and 2
for invalid input or unreadable metrics.

## Gate

The observed P95 delta is:

`mock-sidecar P95 - direct-baseline P95`

- PASS only when the delta is strictly less than 5 ms.
- FAIL when the delta is exactly 5 ms or greater.
- A negative delta passes this arithmetic gate, but does not prove the proxy
  is faster or has zero overhead.

## Independent absolute-latency gate

The comparator also reports an independent absolute aggregate P95 target,
defaulting to strictly less than 50 ms for both the baseline and sidecar.
Override it with `--absolute-p95-threshold-ms` when running the comparator.

- `absolute_latency_status` is PASS only if both P95 values are below the target.
- `baseline_absolute_p95_pass` and `sidecar_absolute_p95_pass` report each run separately.
- The existing `status` and exit codes continue to represent the overhead-delta gate only.
- Absolute-latency results are computed from numeric P95 values. They do not rely
  on the k6 summary's exported threshold metadata.

## Interpretation and limitations

The original workload includes login and multiple authenticated API requests.
The aggregate `http_req_duration` P95 is not an endpoint-only measurement and
may be dominated by login latency. This milestone uses the same aggregate
metric on both sides for consistency, but the delta can still be noisy due to
system load, run order, database state, and request sampling.

The proxy's configured delay is artificial mock data. It is not a measurement
of internal sidecar processing cost, and the observed P95 delta is not a pure
measurement of sidecar overhead. A real eBPF milestone requires repeating
the same controlled workload with the actual sidecar and recording its
configuration, environment, raw summaries, and repeated-run variability.

The existing baseline runner has a `http_req_duration` P95 threshold of less
than 50 ms. It may report a threshold failure because this aggregate includes
login latency. Retain and inspect the raw JSON and console log; do not
reinterpret a failed baseline threshold as a successful performance result.

## Actual benchmark results — 2026-10-21

The direct baseline and mock-sidecar benchmark runs completed and produced
valid k6 JSON summaries. The existing aggregate P95 threshold of less than
50 ms was exceeded in both runs.

| Metric | Direct baseline | Mock sidecar |
|---|---:|---:|
| Aggregate HTTP request P95 | 85.7661309 ms | 122.430898 ms |
| HTTP request failure rate | 0% | 0% |
| k6 checks passing | 100% | 100% |
| Existing aggregate P95 < 50 ms gate | FAIL | FAIL |

The observed aggregate P95 delta was 36.6647671 ms. Under the strict Day 15
gate (`delta < 5 ms`), the result is FAIL. A delta exactly equal to 5 ms also
fails the gate.

Result files:

- `benchmarks/results/day15/day15_baseline_20261021_023313.json`
- `benchmarks/results/day15/day15_mock_sidecar_20261021_023345.json`
- `benchmarks/results/day15/day15_overhead_report.json`

Interpretation and limitations:

- The overhead-gate failure is an observed benchmark result, not a failure
  of the overhead calculator.
- The 50 ms aggregate P95 target and the 5 ms observed-delta gate are separate
  checks; both failed in these runs.
- The measured delta can include workload variability, application-layer
  proxy costs, and the configured mock delay.
- This is a temporary mock-proxy comparison, not a real eBPF overhead
  measurement. Do not present it as evidence that a production eBPF sidecar
  exceeds the 5 ms target.
- Both runs reported zero HTTP request failures and 100% passing k6 checks,
  despite exceeding the latency threshold.

## Acceptance status and real-sidecar handoff

**Milestone status: pipeline-validated-pending-real-hardware.**

The deterministic gate acceptance tests validate that a 2 ms observed P95
delta passes, an 8 ms observed delta fails, and exactly 5 ms fails. These
controlled calculator tests are not substitutes for end-to-end measurements.

The recorded end-to-end mock comparison produced an observed P95 delta of
36.6647671 ms and correctly failed the strict <5 ms gate. Do not relabel that
measurement as a pass. A configured 2 ms delay does not guarantee a 2 ms
observed aggregate P95 delta.

### Real component handoff

The current mock is an application-layer HTTP reverse proxy, not an eBPF
implementation. Members 1/2 must provide the real component's launch command,
health-check behavior, listening-port configuration, and upstream-forwarding
contract before it can replace the mock.

For a compatible component, the intended runner integration is to change the
sidecar launch target/configuration only, retain the same four upstream API
targets and benchmark inputs, and produce the same baseline, sidecar, and
comparison report artifacts. If the real component does not implement the
same HTTP forwarding contract, an adapter or runner change will be required;
zero-code-change replacement cannot be guaranteed before its interface is
known.

After integration, run the same baseline and sidecar workload, calculate the
observed P95 delta with the strict <5 ms comparator, and record the real
component version, configuration, raw JSON files, and result. Only that run
can establish whether real eBPF overhead meets the milestone.


## Configurable sidecar handoff — verified 2026-10-21

The benchmark runner accepts `SIDECAR_LAUNCHER` and `SIDECAR_KIND`.
The mock remains the default. A compatible real-sidecar launcher can be
selected with this configuration:

    SIDECAR_KIND=real SIDECAR_LAUNCHER=/absolute/path/to/real-sidecar-launcher bash benchmarks/run_sidecar_benchmark.sh 5 30s

Replace the example path with the actual executable supplied by Members 1/2.
The launcher must accept `UPSTREAM_URL` and `LISTEN_PORT`, forward HTTP
requests to its upstream, and respond successfully to `GET /health`.
Compatibility and real eBPF identity must be verified before claiming
successful real-sidecar integration.

### Latest short-run measurement — 2026-10-21

- Direct baseline aggregate P95: 72.9874382 ms
- Mock-sidecar aggregate P95: 81.7146962 ms
- Observed P95 delta: 8.7272580 ms
- Strict `<5 ms` gate: FAIL
- HTTP request failure rate: 0% in both runs
- k6 checks: 100% passing in both runs
- Dated comparison report: `benchmarks/results/day15/day15_overhead_report_20261021_031900.json`
- Dated run report: `benchmarks/results/day15/day15_milestone_20261021_031900.md`

This short run is additional evidence that the gate can fail. It is not a
replacement for the longer benchmark, and neither mock result measures real
eBPF overhead.
