# Day 21 — Legitimate Traffic Zero-Drop Verification

## Goal

Run legitimate API traffic concurrently with a BOLA invoice-ID sweep. Verify
that legitimate requests succeed while the test enforcement adapter denies
attack-classified invoice requests after the configured threshold.

## Components

- Billing service: `127.0.0.1:5004`
- Day 21 test adapter: `127.0.0.1:8004`
- Day 20 fail-open wrapper: `127.0.0.1:8005`
- Legitimate traffic: Day 4 `traffic_generator.py`, duration 25 seconds,
  seed 21
- Attack traffic: Day 8 `bola_attack.py`, invoice IDs 1–40

The runner uses a dedicated `logs/day21-traffic` directory and a dedicated
`logs/day21-attack` directory. It writes the result to
`logs/zero_drop_report.json` and process output to `logs/day21-*-process.log`.

## Configuration

The adapter is configured with a threshold of 3 distinct invoice paths in a
10-second window and a 20-second block. Legitimate traffic and attack traffic
use `BILLING_OVERRIDE_URL=http://127.0.0.1:8005`; the wrapper checks the
adapter and routes to it while healthy.

## Run

From the repository root:

```bash
python -m pytest -q appsec-testing/tests/test_day21_zero_drop.py

python appsec-testing/scripts/enforcement/zero_drop_verification.py
```

The runner starts only the adapter and wrapper processes it owns, waits for
the legitimate and attack subprocesses, collects adapter counters and traffic
records, writes a JSON report, and stops its own processes.

## Acceptance criteria

The report passes only if all are true:

1. At least one legitimate request was recorded.
2. Legitimate success rate is exactly `1.0`.
3. Legitimate failure count is zero.
4. At least one attack request was blocked.
5. Enforcement activity was observed.

Review `logs/zero_drop_report.json` and the process logs if the run fails.

## Evidence boundary

**This Day 21 adapter is an application-layer simulation.** It returns HTTP
403 for blocked attack-classified requests. It is not an eBPF program, does
not prove raw-socket closure or kernel packet drops, and must not be described
as kernel-level zero-drop evidence. Day 19 kernel-drop verification is a
separate test and its results must be reported independently.

A passing result means that this controlled application-layer scenario met
the listed acceptance criteria. It does not prove that every possible
legitimate request or production workload will experience zero drops.
