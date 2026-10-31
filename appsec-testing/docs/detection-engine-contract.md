# Real-Time Detection Engine Output Contract

## Purpose

The detection engine identifies anomalous cross-user object access and
emits alerts in real time. The engine may use deterministic rules,
correlation, baselining, or machine-learning techniques.

## Output location

The default alert destination is:

`logs/detection_alerts.jsonl`

The implementation should support a configurable output path. Emit one
JSON object per line (JSONL), and flush alerts promptly so downstream
tools can consume them without waiting for the process to exit.

## Alert schema

Every alert must contain these fields:

```json
{
  "ts": "2026-10-22T08:34:12.345678+00:00",
  "alert_type": "cross_user_object_access",
  "requester_id": 3,
  "distinct_owners_accessed": 3,
  "window_seconds": 10,
  "reason": "Requester 3 accessed invoices belonging to 3 distinct owners within 10 seconds."
}
```

Field requirements:

- `ts`: ISO 8601 timestamp for when the alert was emitted, not when the
  triggering request occurred.
- `alert_type`: `cross_user_object_access`.
- `requester_id`: integer identifying the requester.
- `distinct_owners_accessed`: integer count of distinct owners observed
  within the detection window.
- `window_seconds`: numeric duration of the detection window.
- `reason`: human-readable explanation of the detection.

## Minimum detection rule

Flag a requester who accesses invoices or orders belonging to at least
3 distinct owner IDs within a 10-second sliding window.

Only confirmed cross-user accesses count toward this rule. Accesses to
the requester's own objects must not contribute to the threshold.

A real detection engine may implement additional rules, but it must be
at least as sensitive to this minimum pattern.

## Real-time requirement

Alerts must be emitted within 15 seconds of the start of the triggering
attack in the Day 16 milestone test, and promptly after the threshold
is crossed. A periodic batch job that only processes events every few
minutes does not satisfy this milestone.

The milestone test measures time to detection, checks the attacker's
identity, and checks for false-positive alerts during concurrent
legitimate traffic.

## Evidence and limitations

The initial implementation is explicitly a temporary mock, not the
production anomaly/correlation engine. The mock demonstrates that the
minimum rule and measurement pipeline can work against the billing
service's structured access logs.

A fixed threshold over a single short window can be evaded by a patient
attacker who spreads accesses over time. The real engine should consider
multiple windows and longer-horizon correlation.

## Replacement compatibility

The real engine must preserve the output schema and configurable output
destination. The Day 16 milestone grader should be able to launch the
replacement engine by changing its configured launch command, without
changing the alert-grading rules.
