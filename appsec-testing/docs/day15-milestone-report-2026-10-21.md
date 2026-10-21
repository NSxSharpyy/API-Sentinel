# Day 15 Latency Milestone Report

**Date:** 2026-10-21  
**Milestone status:** `pipeline-validated-pending-real-hardware`  
**Real eBPF performance verified:** No

## Acceptance summary

| Acceptance check | Result |
|---|---|
| Baseline-to-sidecar benchmark workflow | Executed |
| Strict observed P95 delta gate | Implemented |
| Controlled 2 ms observed delta | PASS |
| Controlled 8 ms observed delta | FAIL, as required |
| Exact 5.0 ms boundary | FAIL, as required |
| Original Day 5 benchmark scripts modified | No |
| Real eBPF sidecar tested | Pending |

The controlled checks validate the comparator. They do not establish that a
sidecar configured with a 2 ms delay will produce an end-to-end observed delta
of 2 ms.

## Recorded end-to-end mock comparison

| Measurement | Direct baseline | Mock sidecar |
|---|---:|---:|
| Aggregate HTTP request P95 | 85.7661309 ms | 122.430898 ms |
| HTTP request failure rate | 0% | 0% |
| k6 checks passing | 100% | 100% |
| Existing aggregate P95 < 50 ms target | FAIL | FAIL |

**Observed P95 delta:** 36.6647671 ms  
**Required gate:** strictly less than 5.0 ms  
**Comparison result:** FAIL

The failed latency gates are genuine results and must not be changed to PASS.
The observed delta includes application-layer mock-proxy costs and run-to-run
variability; it is not a measurement of intrinsic eBPF overhead.

## Evidence files

- `benchmarks/results/day15/day15_baseline_20261021_023313.json`
- `benchmarks/results/day15/day15_mock_sidecar_20261021_023345.json`
- `benchmarks/results/day15/day15_overhead_report.json`
- `docs/day15-milestone-latency.md`

## Handoff to Members 1/2

The temporary sidecar is an application-layer HTTP reverse proxy, not a real
eBPF component. Before replacing it, obtain the real component's launch
interface, port configuration, health-check contract, and upstream-forwarding
behavior. The current runner can be reused unchanged only if that component
matches its existing interface; otherwise, an adapter or runner modification
will be required. A guaranteed one-line swap has not yet been verified.

After integration, rerun the baseline and sidecar workloads, preserve the raw
JSON results, and calculate the same strict P95 delta. Only that real-component
run can validate the final performance milestone.

## Latest longer mock run — 2026-10-21

| Measurement | Direct baseline | Mock sidecar |
|---|---:|---:|
| Aggregate HTTP request P95 | 92.2502172 ms | 132.3065731 ms |
| Absolute P95 target (<50 ms) | FAIL | FAIL |

- Observed P95 delta: 40.0563559 ms
- Strict overhead target (<5 ms): FAIL
- HTTP request failures: 0% in both runs
- k6 checks passing: 100% in both runs
- Baseline JSON: `benchmarks/results/day15/day15_baseline_20261021_103955.json`
- Mock-sidecar JSON: `benchmarks/results/day15/day15_mock_sidecar_20261021_104027.json`
- Overhead report: `benchmarks/results/day15/day15_overhead_report_20261021_104027.json`

The exported k6 threshold metadata marked `p(95)<50` as passing despite
numeric P95 values above 50 ms. The independent numeric gates are authoritative
for this milestone report. The mock is not a real eBPF measurement.
