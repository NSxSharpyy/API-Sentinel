# API-Sentinel Kernel Enforcement Certification

**Validation date:** 2026-10-31
**Certification result:** PASS
**Scope:** Controlled Day 19 and Day 23 TC/eBPF loopback experiments

## 1. Objective

Record the evidence supporting API-Sentinel's controlled kernel-level
packet-drop certification.

The certification combines:

- Day 19: a controlled TC/eBPF packet-drop observation.
- Day 23: a concurrent TC/eBPF SYN-drop workload with per-source-port
  evidence and verified cleanup.
- A read-only evaluator that validates both evidence reports and their
  cleanup results.

This certification is limited to the tested local environment and workload.

## 2. Day 19 — Controlled kernel-drop observation

Evidence report:

`appsec-testing/logs/day19_kernel_drop_report.json`

Recorded result:

- Overall status: `OBSERVED`
- Interface: `lo`
- Destination port: `5004`
- Packets seen: 8
- Packets matched: 5
- Packets dropped: 5
- Map dump return code: 0
- Client result: response timeout
- Filter deletion: return code 0
- Qdisc deletion: return code 0
- Cleanup: complete

The observed matched and dropped counters agree.

This establishes a controlled packet-drop observation. Packet counters
represent packets, not necessarily individual HTTP requests. Retransmissions
and the limited loopback test scope prevent treating this result alone as
per-request enforcement proof.

## 3. Day 23 — Concurrent kernel-drop workload

### Test implementation

- BPF program: `appsec-testing/scripts/enforcement/day23_concurrent_syn_drop.c`
- Runner: `appsec-testing/scripts/enforcement/run_day23_concurrent_kernel_drop.py`
- Interface: `lo`
- Destination TCP port: `5084`
- Concurrent workers: 50
- Connection attempts: 100
- Source-port range: 40000–40099

The classifier matches initial TCP SYN packets directed to the test port,
records per-source-port activity, increments matched and dropped counters,
and returns `TC_ACT_SHOT`.

### Execution

Run from the repository root:

```bash
sudo python appsec-testing/scripts/enforcement/run_day23_concurrent_kernel_drop.py
```

### Recorded workload results

- Attempts completed: 100/100
- Outcomes: 100 timeouts
- Kernel counters: 104 seen, 100 matched, 100 dropped
- Expected source ports: 100
- Observed source ports: 100
- Each expected source port recorded exactly one hit.
- Filter ownership verified against the attached program ID.
- Filter deletion and qdisc deletion returned code 0.
- Pinned-object cleanup successful.
- Overall cleanup complete.

All six workload checks passed:

- `workload_completed`
- `all_attempts_timed_out`
- `drop_accuracy_passed`
- `source_port_coverage_passed`
- `cleanup_complete`
- `no_runtime_error`

## 4. Evidence evaluation

Run the read-only evaluator:

```bash
python appsec-testing/scripts/enforcement/evaluate_kernel_blocking_at_scale.py \
  --day19-report appsec-testing/logs/day19_kernel_drop_report.json \
  --concurrency-report appsec-testing/logs/day23_kernel_blocking_at_scale_report.json \
  --out appsec-testing/logs/day23_kernel_certification_report.json
```

Recorded result:

- `kernel_certification: PASS`
- `concurrency_status: PASS`
- `overall: PASS`
- All eight evaluator checks passed.
- Targeted evaluator tests: 34 passed.

## 5. Certification scope and limitations

This PASS applies only to the controlled Day 19 and Day 23 experiments.

It does not establish:

- Production deployment reliability or performance.
- Reliability under arbitrary traffic volumes or workloads.
- Compatibility with every kernel or network configuration.
- Hardware-offloaded enforcement.
- TC/eBPF daemon fail-open behavior.
- Per-request blocking proof for the Day 19 HTTP workload.

The Day 23 test used loopback (`lo`) and a controlled local TC/eBPF SYN-drop program. Its results must not be generalized beyond that tested environment.

## 6. Certification decision

**Controlled Day 19 and Day 23 kernel evidence: PASS.**

This is not an unconditional Phase 3 freeze or production enforcement sign-off. Refer to `docs/phase3-freeze.md` for the overall CONDITIONAL Phase 3 decision.
