# Day 30 — API-Sentinel Live Demo Runbook

## 1. Objective

Rehearse a repeatable, non-interactive demonstration of API-Sentinel's
security testing and monitoring capabilities.

The demonstration contains eight segments and has a target runtime of
12 minutes. The segment budgets total 10 minutes 30 seconds, leaving
approximately 90 seconds for transitions and minor delays.

This is an authorized local training lab. Do not expose the intentionally
vulnerable services to public networks.

## 2. Environment and safety

Repository:
- `~/API-Sentinel-recovery`

Branch:
- `appsec-rate-limit`

Current recovery-stack host ports:
- Auth: `5101`
- User: `5102`
- Order: `5103`
- Billing: `5104`

Expected service health endpoints:
- `http://127.0.0.1:5101/health`
- `http://127.0.0.1:5102/health`
- `http://127.0.0.1:5103/health`
- `http://127.0.0.1:5104/health`

The rehearsal must not:
- Run `docker compose down -v` or delete persistent volumes.
- Kill processes that it did not start.
- Terminate unrelated Docker or Podman services.
- overwrite existing evidence or reports.
- claim application-layer simulation is kernel-level enforcement.
- claim partial OWASP coverage is full coverage.

Use unique per-run output directories under:
`appsec-testing/logs/day30_rehearsals/`

## 3. Pre-demo checklist

1. Confirm the current Git branch and working-tree status.
2. Confirm the four application services are already running.
3. Check all four health endpoints and require HTTP 200.
4. Confirm the local seeded customer data is available.
5. Confirm the Day 23 kernel certification evidence exists.
6. Confirm the Day 20 fail-open verifier and its dependencies exist.
7. Check ports 8004, 8005, and 8006 are free before Day 20 verification.
8. Create a unique rehearsal output directory.
9. Do not rebuild or tear down the existing stack during a rehearsal.

If the application stack is unavailable, use the documented prewarmed
Compose startup procedure without deleting volumes. If startup fails,
stop the live sequence and use the recorded evidence fallback.

## 4. Eight-segment demonstration

### Segment 1 — Platform startup and health
**Budget: 90 seconds**

Objective:
Show that the API-Sentinel target services are available.

Actions:
- Verify auth, user, order, and billing health endpoints.
- Record status codes and response times.
- Do not rebuild or recreate containers during the rehearsal.

Pass condition:
All four services return HTTP 200 from their health endpoints.

Recovery:
If a service is unhealthy, inspect its own container logs and health
state. Use the existing Compose startup procedure without removing
volumes. If recovery exceeds the time budget, use the recorded reports
and mark the live segment as failed or skipped.

### Segment 2 — Manual BOLA demonstration
**Budget: 60 seconds**

Objective:
Demonstrate authenticated access to an invoice without an ownership
check.

Endpoints:
- `POST /api/v2/auth/login`
- `GET /api/v2/billing/invoices/1`
- `GET /api/v2/billing/invoices/5`

Actions:
1. Authenticate as the seeded Alice customer using the local lab
   credentials.
2. Extract the returned Bearer token.
3. Request invoice 1 and invoice 5 using that token.
4. Inspect the invoice owner and requester identity.

Pass condition:
The response demonstrates cross-user invoice access when the
requester does not own the requested invoice.

Evidence:
Record HTTP status, invoice identifier, owner identifier, and requester
identifier. Do not write passwords or Bearer tokens into reports.

Recovery:
If authentication fails, verify the seeded account and credentials.
Do not invent credentials or weaken authentication checks during the
demo.

### Segment 3 — Automated BOLA sweep
**Budget: 90 seconds**

Runner:
`scripts/attacks/bola_attack.py`

Expected invocation:
`--mode sweep --start-id 1 --end-id 50`

Objective:
Demonstrate automated enumeration of invoice identifiers using the
intentionally vulnerable local billing endpoint.

Pass condition:
The runner completes and produces its attack report.

Record:
- Exit code.
- Number of requests.
- Number of successful cross-user accesses.
- Number of failed or inaccessible identifiers.
- Output report path.

The expected result is approximately 45 compromised invoices in the
original task description. This is an expectation, not a hardcoded
pass condition. Report the actual measured result.

Recovery:
If no cross-user access is observed, verify the seeded data and the
intentional BOLA route before the live presentation. Do not modify
authorization behavior during the rehearsal.

### Segment 4 — Real-time detection
**Budget: 120 seconds**

Runner:
`scripts/detection/realtime_flagging_test.py`

Objective:
Show the Day 16 mock detection engine observing a BOLA sweep and
generating a cross-user access alert.

Use the runner's bounded timeout and the configured local service
ports. Preserve its temporary, per-run evidence directory.

Pass condition:
- The attack executes.
- An alert is generated within the configured timeout.
- The alert identifies cross-user object access.
- The report records the actual detection latency.

Important:
This is a mock detection-engine demonstration. Do not describe it as
a production detection deployment.

Recovery:
If no alert appears within 10 seconds, inspect the runner report and
engine log. Verify the sweep range and detection threshold. If the
live alert cannot be demonstrated within the segment budget, show
the recorded Day 16 evidence and label the live attempt accurately.

### Segment 5 — Enforcement evidence
**Budget: 120 seconds**

Objective:
Present evidence that the tested TC/eBPF packet-drop path works under
the recorded Day 23 concurrent workload.

Primary evidence:
- `logs/day23_kernel_blocking_at_scale_report.json`
- `logs/day23_kernel_certification_report.json`

Show:
- Evidence type and kernel-drop proof fields.
- Concurrent workload result.
- Matched and dropped packet counters.
- Cleanup status.

Pass condition:
The recorded certification reports successful kernel-drop evidence
and completed cleanup.

Scope limitation:
The Day 23 certification concerns the tested loopback TC/eBPF SYN-drop
workload. It is not proof of production network enforcement or of
blocking traffic to the billing application port.

Do not substitute the Day 20 HTTP proxy simulation for kernel-drop
evidence.

Recovery:
If a live enforcement demonstration is unavailable, present the
recorded Day 23 evidence. Do not claim that a live packet drop occurred
during this rehearsal unless it was actually executed and measured.

### Segment 6 — Fail-open behavior
**Budget: 60 seconds**

Runner:
`scripts/enforcement/fail_open_verification.py`

Objective:
Demonstrate the Day 20 fail-open behavior using the existing HTTP
simulation.

For the current recovery stack, configure:
- `DAY20_BILLING_URL=http://127.0.0.1:5104`
- `DAY20_ENFORCER_UPSTREAM_URL=http://127.0.0.1:5104`
- `DAY20_DIRECT_UPSTREAM_URL=http://127.0.0.1:5104`

Pass condition:
The verifier completes and records its checks and report.

Scope limitation:
This is an application-layer HTTP simulation. It does not prove
fail-open behavior of a real TC/eBPF daemon.

Recovery:
If ports 8004, 8005, or 8006 are occupied, do not terminate unknown
processes. Record the segment as unavailable and present existing
Day 20 evidence if available.

### Segment 7 — OWASP API Security regression
**Budget: 60 seconds**

Runner:
`scripts/compliance/owasp_top10_regression.py`

Objective:
Show the regression results and category-level coverage for the
OWASP API Security Top 10 (2023).

Use a unique report path for each rehearsal.

Record:
- Overall status.
- Test execution status.
- Passed, failed, and error counts.
- Per-category status.
- Weighted coverage percentage and denominator.

Coverage interpretation:
- COVERED contributes 1.0.
- PARTIAL contributes 0.5.
- FAILED, BLOCKED, and NOT_RUN contribute 0.
- OUT_OF_SCOPE is excluded from the denominator.

Do not describe six categories as fully covered unless the actual
report marks all six as COVERED.

Pass condition:
The regression command completes and the resulting report is readable.
A PARTIAL coverage result must remain PARTIAL.

Recovery:
If the regression exceeds the segment budget, preserve its output and
show the latest valid report, clearly identifying whether it belongs
to the current rehearsal or an earlier run.

### Segment 8 — Close and evidence summary
**Budget: 30 seconds**

Objective:
Summarize the measured results and their limitations.

Reference:
- `docs/Performance_Security_Validation_Report.md`
- Current rehearsal's unique reports and logs.
- Day 23 kernel certification evidence.

The rehearsal summary must distinguish:
- Live checks executed during this rehearsal.
- Recorded evidence from earlier days.
- Mock or application-layer simulations.
- Failed, skipped, and unavailable segments.

Do not overwrite the existing security validation report.

## 5. Timing and reliability

Target total duration: 12 minutes.

| Segment | Budget |
|---|---:|
| Platform health | 90 seconds |
| Manual BOLA | 60 seconds |
| Automated BOLA sweep | 90 seconds |
| Real-time detection | 120 seconds |
| Kernel enforcement evidence | 120 seconds |
| Fail-open simulation | 60 seconds |
| OWASP regression | 60 seconds |
| Close | 30 seconds |
| **Segment budget** | **630 seconds** |
| **Transition and recovery buffer** | **90 seconds** |
| **Total** | **720 seconds** |

Perform at least three rehearsals. Preserve each run's timestamp,
segment status, duration, output paths, and error details.

A segment that is skipped or replaced by recorded evidence must not
be counted as a successful live execution.

## 6. Recovery and abort rules

- Health check failure: inspect service-specific logs; do not delete
  volumes or force-stop unrelated processes.
- BOLA sweep returns no cross-user access: verify seeded data and
  endpoint behavior before presenting.
- No detection alert: inspect the mock engine log and report; use
  recorded evidence with an explicit label if necessary.
- Day 23 live evidence unavailable: use the saved certification
  report and identify it as previously recorded evidence.
- Day 20 ports occupied: do not kill unknown processes; skip the live
  simulation and report why.
- OWASP command exceeds its budget: retain partial output and use a
  clearly dated prior report only as historical evidence.
- Complete application outage: stop live requests and use the
  validation report and saved JSON evidence.

## 7. Sign-off criteria

The rehearsal is complete when:
1. Three rehearsal runs have been recorded.
2. Each run has a machine-readable report.
3. Segment durations and statuses are available.
4. Flaky or failed segments are documented.
5. The regression suite has been executed.
6. The results document accurately distinguishes live results from
   historical evidence and simulations.
7. Existing project changes and evidence have been preserved.
