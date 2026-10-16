# Changelog — AppSec, Attack Simulation & Testing

## Phase 1 — October 8–16, 2026

Status: Technical validation passed; formal team sign-off and release steps
are tracked separately.

- Day 1: Scaffolded four mock microservices (auth, user, order, billing) with
  request tracing, JSON logging, and safe error handling.
- Day 2: Containerized the services and established token authentication and
  the intentional billing invoice BOLA test case.
- Day 3: Added a seeded SQLite database for multi-tenant customers, orders,
  and invoices.
- Day 4: Added a legitimate background traffic generator that exercises
  customer-scoped behavior.
- Day 5: Added a k6 benchmark harness and documented baseline measurements.
- Day 6: Added pipeline integrity auditing and temporary mock ingestion and
  forwarding components.
- Day 7: Added the Phase 1 validation harness, authenticated benchmark
  acceptance checks, regression tests, and freeze evidence.

### Day 7 validation evidence

- Result: PASS
- Checks passed: 13
- Checks failed: 0
- Report: `docs/phase1-freeze-report.json`
- Dated evidence copy: `docs/phase1_freeze_report_2026-10-16.json`
- Sign-off document: `docs/phase1-freeze.md`

### Negative-test evidence

- The temporary billing owner-check negative test was performed on
  2026-10-16. The retained pytest log at
  `appsec-testing/logs/phase1-run-20261016-075031/pytest.log` records the
  expected failure of `test_billing_bola_vulnerability_is_present`
  (1 failed, 69 passed).
- The complete negative-run validator JSON was not retained.
- After restoring the intentional BOLA lab behavior, the final validator
  passed all 13 checks.

### Outstanding release tasks

- Obtain the required project-owner/team sign-off.
- Review the intended change set, including untracked backup files.
- Commit and push the approved change set only when explicitly authorized.
