# Day 29 — Deployment Orchestration Validation

## Objective

Validate project-scoped cleanup, cold image builds, seed execution,
application startup ordering, service health checks, and authenticated
end-to-end application behavior.

## Implementation

- Runner: `appsec-testing/scripts/deployment/deployment_orchestration_test.py`
- Tests: `appsec-testing/tests/test_day29_deployment.py`
- JSON report: `appsec-testing/logs/deployment_orchestration_report.json`

The destructive workflow requires the explicit `--execute` argument.
Cleanup is scoped to the `api-sentinel-recovery` Compose project.

The recovery Compose project uses host ports 5101–5104. The original
system-Docker API-Sentinel services on ports 5001–5004 were preserved.

## Focused tests

Command:

`python -m pytest -q appsec-testing/tests/test_day29_deployment.py`

Result: **15 passed.**

## Deployment execution

The runner was executed with `--execute`.

Overall result: **PASS**  
Elapsed time: **37.945 seconds**

| Step | Result |
|---|---|
| Project-scoped teardown | PASS |
| Post-teardown inventory | PASS |
| Cold image build and deployment | PASS |
| Seed container exit status | PASS — exit code 0 before application startup |
| Application health checks | PASS — all four services returned HTTP 200 and healthy status |
| Authentication and token flow | PASS |
| Profile, orders, and invoices E2E checks | PASS |
| Ownership checks | PASS |

The cold deployment step completed in 24.664 seconds. The runner
completed the authenticated end-to-end checks, including ownership
verification for the application resources.

The original system-Docker API-Sentinel containers were preserved.

## Full AppSec test suite

Command:

`python -m pytest -q appsec-testing/tests`

Result: **437 passed in 19.99 seconds.**

## Day16 detection regression validation

The focused Day16 detection milestone tests were rerun with the
appropriate Python import path.

Result: **12 passed.**

The Day16 service-port routing changes were also included in the
full AppSec regression suite.

## Conclusion

Day29 deployment orchestration validation passed. The runner completed
project-scoped teardown and inventory checks, cold deployment, seed
ordering, health checks, authenticated end-to-end behavior, and
ownership verification.

The focused Day29 tests and full AppSec regression suite passed.
The focused Day16 detection tests also passed.

## Evidence

- `appsec-testing/logs/deployment_orchestration_report.json`
- Day29 focused tests: 15 passed
- Day16 focused tests: 12 passed
- Full AppSec tests: 437 passed
