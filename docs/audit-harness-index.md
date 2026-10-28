# API-Sentinel Audit Harness Index

## Purpose

The Day 14 Phase 2 audit harness validates the security lab's intentional BOLA behavior, privilege-escalation test matrix, planted shadow/zombie endpoints, discovery scanner, multi-threat simulation, and regression suite.

## Entry points

| Resource | Purpose |
|---|---|
| `appsec-testing/scripts/run_audit_suite.sh` | Runs Phase 1 followed by Phase 2; stops on failure |
| `appsec-testing/scripts/validate_phase1.py` | Runs the Phase 1 validation suite |
| `appsec-testing/scripts/validate_phase2.py` | Runs the end-to-end Phase 2 validation |
| `appsec-testing/scripts/check_health.py` | Checks the four API health endpoints |
| `appsec-testing/scripts/attacks/bola_attack.py` | Exercises the intentional BOLA lab scenario |
| `appsec-testing/scripts/attacks/privesc_attack.py` | Exercises the privilege-escalation matrix |
| `appsec-testing/scripts/recon/endpoint_scanner.py` | Scans for the planted discovery surface |
| `appsec-testing/scripts/recon/verify_discovery.py` | Grades discovery output against the ground-truth manifest |
| `appsec-testing/scripts/simulation/multi_threat_simulation.py` | Runs the multi-threat simulation |
| `appsec-testing/docs/shadow_zombie_manifest.md` | Ground-truth shadow/zombie endpoint manifest |
| `appsec-testing/tests/` | Regression and validation tests |

## Latest validation evidence

- Date: 2026-10-20
- Result: PASS
- Passed: 9
- Failed: 0
- Skipped: 0
- Report: `appsec-testing/logs/phase2_freeze_report.json`
- Run evidence: `appsec-testing/logs/phase2-run-20261020T180547Z`
- Freeze summary: `docs/phase2-freeze.md`

The report and evidence directory above refer to the successful run. Run the validator again to produce a fresh report for a new validation attempt.

Combined audit-suite log: `appsec-testing/logs/audit-suite-20261020T180430Z.log` (both validators passed on 2026-10-20; Phase 2 reported 184 passing pytest tests).

## Running the validator

From the `appsec-testing` directory, run the combined suite with:

```bash
./scripts/run_audit_suite.sh
```

To run Phase 2 by itself, use:

```bash
python scripts/validate_phase2.py --help
python scripts/validate_phase2.py
```

The help command displays usage without launching the audit. The audit rebuilds the containerized stack and runs the validation suite. It is designed not to delete Docker volumes.

## Interpreting the result

A passing audit means all nine checks passed in that run. A failed or skipped check prevents the report from being treated as a full pass.

The mock discovery-verification check validates the grader's behavior against a deliberately imperfect fixture. It does not prove that Member 3's real discovery engine achieves 100% shadow-endpoint recall or correctly classifies every zombie API.

## Outstanding work

- Obtain and validate Member 3's real discovery-engine output against the manifest.
- Confirm the required shadow-endpoint recall and zombie-classification criteria.
- Obtain project-owner/team sign-off before release.
- Review untracked backups and the intended change set before any commit or push.

No commit, push, or release sign-off is performed by the audit harness.
