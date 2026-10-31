# Day 16 — Real-Time Detection Milestone

## Objective

Validate the real-time flagging measurement pipeline against the temporary
mock detection engine while exercising the local API-Sentinel BOLA lab.

## Detection contract

- Event source: structured billing-service logs.
- Qualifying event: `invoice accessed` with `cross_user_access: true`.
- Correlation key: `requester_id`.
- Threshold: at least 3 distinct `owner_id` values.
- Sliding window: 10 seconds.
- Alert type: `cross_user_object_access`.
- Default alert destination: `logs/detection_alerts.jsonl`.
- Target: alert within 15 seconds of attack start.
- Duplicate policy: at most one alert per requester per engine process.

## Implementation

- `scripts/detection/mock_detection_engine.py` tails billing Compose logs
  and emits contract-shaped JSONL alerts.
- `scripts/detection/realtime_flagging_test.py` starts the mock, launches
  a BOLA sweep in a fresh output directory, and records the alert latency.
- `docs/detection-engine-contract.md` defines the alert interface.

## Recorded integration result

Run directory:
`logs/realtime_flagging_wo5wt6kr/`

Observed result:
- Status: PASS
- Attack records: 30
- Confirmed cross-user records: 28
- Distinct cross-user owners in the attack output: 9
- Alert threshold reported: 3 distinct owners
- Requester ID matched the attacker's ID
- Measured attack-start-to-alert latency: 0.5951 seconds
- Target: 15 seconds
- Attack harness exit code: 0

The report is stored in
`logs/realtime_flagging_wo5wt6kr/realtime_flagging_report.json`.

## Scope and limitations

**MOCK DATA — TEMPORARY.** This result validates the measurement pipeline
against the mock engine and the local vulnerable lab. It does not establish
the accuracy, coverage, or latency of a production detection engine.

The current mock correlates billing invoice-access events. Order-access
correlation is not implemented in this mock.

The latency measurement starts immediately before launching the attack
subprocess, so it includes subprocess startup time. It is a practical
end-to-end milestone measurement, not a precise measurement of internal
detector processing time.

## Remaining validation

- Add unit tests for threshold, distinct-owner counting, window expiry,
  malformed events, and legitimate-access exclusion.
- Add an integration test that skips when the local Compose stack is
  unavailable.
- Run a legitimate-only negative test and confirm no alert is emitted.
- Run the complete relevant pytest suite.
- Replace the mock with the production detection engine when available,
  keeping the same alert contract and rerunning the milestone checks.

## Git status

No commit or push is implied by this report. Review and stage only the
intended Day 16 files when explicitly authorized.
