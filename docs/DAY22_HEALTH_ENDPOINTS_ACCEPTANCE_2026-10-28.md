# Day 22 — System Health Inspection Endpoints

Validation date: 2026-10-28

## Implemented

- `GET /healthz`: returns HTTP 200 while the API process can answer.
- `GET /readyz`: returns HTTP 200 when capture, persistence worker, and
  HTTP pipeline are active; otherwise returns HTTP 503.
- Memory snapshot: process RSS and system memory utilization when Linux
  `/proc` metrics are available.
- Queue snapshot: current depth and capacity for raw packet, header,
  metadata, and persistence queues.

## Verification

- Focused health and Day 1 tests: 13 passed.
- Full test suite: 258 passed, 1 existing Starlette/httpx deprecation warning.
- `compileall` and `git diff --check` passed.

## Acceptance boundary

Health endpoint behavior has been verified by automated tests, including
ready and not-ready states. A live operational health check under the active
capture daemon has not yet been recorded. Readiness currently evaluates
worker task states and pipeline initialization; it does not independently
probe database connectivity.
