# Day 13 — Multi-Threat Attack Simulation

## Purpose

Run the API-Sentinel lab's legitimate traffic generator, BOLA sweep, endpoint
discovery scanner, mock ingestion receiver, and mock packet forwarder in one
coordinated simulation.

The runner is intended for the local lab only. It accepts
`http://127.0.0.1` as the API base URL and expects the four API services to be
available on ports 5001–5004. The mock ingestion receiver uses port 5099.

## Components

- **Legitimate traffic:** `scripts/traffic/traffic_generator.py`
- **BOLA sweep:** `scripts/attacks/bola_attack.py`
- **Endpoint discovery:** `scripts/recon/endpoint_scanner.py`
- **Mock ingestion:** `scripts/pipeline/mock_ingestion_pipeline.py`
- **Mock packet forwarding:** `scripts/pipeline/mock_packet_forwarder.py`
- **Pipeline audit:** `scripts/pipeline/pipeline_audit.py`

The runner samples the `/health` endpoints of auth, user, order, and billing
approximately every two seconds while the producers are active.

## Prerequisites

1. Activate the project's virtual environment.
2. Start the Compose services from the repository root.
3. Verify the four API services are healthy.
4. Ensure port 5099 is free. The runner refuses to reuse an existing HTTP
   receiver.
5. Do not run another endpoint scanner concurrently; it writes fixed files
   under `logs/`.

Example:

```bash
cd ~/API-Sentinel
docker compose up -d
cd appsec-testing
source .venv/bin/activate
python scripts/check_health.py
```

## Normal simulation

```bash
python scripts/simulation/multi_threat_simulation.py \
  --duration 30 \
  --bola-end-id 40 \
  --scanner-delay 0.05
```

Each run writes evidence to a timestamped directory under
`logs/multi_threat_runs/`. The root `multi_threat_report.json` summarizes the
run or runs.

## Negative test

Only run this when it is safe to interrupt the lab's billing service:

```bash
python scripts/simulation/multi_threat_simulation.py \
  --duration 30 \
  --bola-end-id 40 \
  --negative-test
```

The negative scenario stops billing temporarily, waits for the failure window,
restarts it, waits for health recovery, and then runs a separate normal
simulation. The runner also attempts to start billing in its cleanup path.
Check `billing_final_health` and the final service health before continuing
other work.

## Evidence

A run directory may contain:

- `traffic.log`, `traffic_*.jsonl`, and `traffic_*.csv`
- `sent_requests.jsonl`
- `bola.log` and `bola_attack.jsonl`
- `scanner.log`, `discovery_scan.jsonl`, and `discovery_report.json`
- `ingestion.log`, `forwarder.log`, and `captures.jsonl`
- `health_samples.jsonl`
- `audit.log` and `audit_report.json`
- `multi_threat_report.json`

The scanner's pre-existing `logs/discovery_scan.jsonl` and
`logs/discovery_report.json` are copied into the run evidence before scanning,
then restored afterward.

## Interpreting the pipeline audit

The pipeline audit compares the traffic generator's `sent_requests.jsonl`
against the receiver's `captures.jsonl`. A PASS with a 100% capture rate means
the records represented in that sent log were captured according to the
audit's request-ID and duplicate checks.

The BOLA attack and endpoint scanner maintain separate evidence logs. Their
requests are **not automatically part of this pipeline capture percentage**.
Do not interpret a 100% pipeline audit as proof that every attack or scanner
probe was captured.

Review JSONL integrity, component exit codes, health samples, the audit report,
and any errors before declaring the run successful.

## Tests

Run the focused tests first:

```bash
python -m pytest tests/test_day13_multi_threat.py -q
python -m pytest tests/test_day6_pipeline_audit.py -q
```

Then run the full suite:

```bash
python -m pytest -q
```

The number of passing tests depends on the current repository state; use the
actual pytest summary rather than an expected count copied from an older task
sheet.
