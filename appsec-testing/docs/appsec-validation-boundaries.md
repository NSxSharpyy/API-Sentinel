# API-Sentinel AppSec Validation Boundaries

## Purpose
Distinguish unit tests, local mock integration, controlled kernel experiments, and production validation. Historical reports are not fresh test results.

## Current evidence
- Targeted Day 16/BOLA/Day 13 tests: 45 passed in 8.23 seconds (reported).
- Full test suite: 261 passed in a previous run (reported; rerun before sign-off).
- Day 18: 15 tests passed in a previous run (reported).
- Day 16: historical local mock-engine report recorded 30 attack records, 28 confirmed cross-user events, and 0.5951-second alert latency. This is not a production guarantee.
- Day 19: controlled lab reported 5 packet matches and 5 drops. Packet counts are not unique HTTP-request counts.
- Day 20: application-layer wrapper demonstrated bypass after the mock enforcer process was killed. This does not prove automatic fail-open behavior in a real TC/eBPF datapath.
- Production deployment: NOT VERIFIED.
- Production detection-engine acceptance: PENDING.

## Day 16 — BOLA detection
Tests cover distinct-owner thresholds, repeated-owner rejection, own-data and unrelated-event exclusion, invalid identifiers, sliding-window expiry, alert timing, and a legitimate-traffic negative control. The documented engine is a local mock. Do not claim production accuracy or latency from these results.

## Day 18 — Rate limiting
The mock limiter and validator provide local evidence for configured rate limiting, recovery, negative controls, and storage-failure handling. Production storage, concurrency, deployment, and failure behavior require separate validation.

## Day 19 — Packet dropping
Treat this as a controlled lab experiment. A timeout alone does not prove application bytes were never received. Check filter attachment, counters, billing logs, cleanup, and service health. Inspect ambiguous attachment state before drawing conclusions. See [Day 19 verification](day19-kernel-drop-verification.md).

## Day 20 — Fail-open
The wrapper checks mock-enforcer process availability and bypasses to billing when unavailable. This does not establish fail-open behavior in the actual TC/eBPF datapath. See [Day 20 verification](day20-fail-open-verification.md).

## Historical evidence
Preserve timestamps and scope of Phase 2 freeze and multi-threat reports. Older PASS results are not current-run guarantees. See [Phase 2 freeze](../../docs/phase2-freeze.md) · [Phase 2 freeze report](../logs/phase2_freeze_report.json).

## Reproducible validation
From `appsec-testing/`, run:
- `python -m pytest -q tests/test_day16_detection_milestone.py`
- `python -m pytest -q tests/test_bola_detector.py`
- `python -m pytest -q tests/test_day13_multi_threat.py`
- `python -m pytest -q tests/test_day18_rate_limiting.py`
- `python -m pytest -q`

From the repository root, run `git diff --check` and `git status --short`. Record actual outputs and timestamps. Do not substitute historical results for a fresh run.

## Release and Git safeguards
- [ ] Rerun the full test suite.
- [ ] Verify reports against source logs and timestamps.
- [ ] Verify kernel cleanup after privileged experiments.
- [ ] Keep mock and production claims distinct.
- [ ] Review every intended file before staging.
- [ ] Do not commit or push without explicit authorization.
