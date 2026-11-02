# Day 26 — OWASP API Security Top 10 (2023) Regression Mapping

## 1. Objective

This document maps existing API-Sentinel security tests and historical evidence to the ten OWASP API Security Top 10 (2023) categories.

The purpose of Day 26 is to consolidate existing evidence into a repeatable regression suite. It does not introduce new vulnerability discovery or claim production certification.

**Important:** `COVERED` means relevant scenarios are tested. It does not mean the application passed those security checks or has no vulnerabilities. Some tests intentionally verify known vulnerable legacy behavior.

## 2. Regression execution

Runner: `scripts/compliance/owasp_top10_regression.py`

Runner tests: `tests/test_day26_owasp_regression.py`

Generated report: `logs/owasp_regression_report.json`

Execute from the `appsec-testing` directory:

```bash
python scripts/compliance/owasp_top10_regression.py
```

## 3. Regression scope and safety

The default runner executes selected existing pytest modules and reads historical evidence. It does not launch live attack scripts, perform endpoint discovery against running services, or execute the mutating Day 25 PII audit.

## 4. OWASP category mapping

### API1 — Broken Object Level Authorization (BOLA)

**Status: COVERED**

Evidence:
- `tests/test_day2_auth_bola.py`
- `tests/test_day8_bola_attack.py`
- `tests/test_day10_shadow_zombie.py`

Tests cover cross-user invoice access, object ownership, order authorization, legacy routes and BOLA scanner behavior.

**Limitations:** Some scanner tests use mocked responses. Coverage is limited to implemented local lab endpoints. `COVERED` does not mean known vulnerable legacy routes have been fixed.

### API2 — Broken Authentication

**Status: PARTIAL**

Evidence:
- `tests/test_day2_auth_bola.py`
- `tests/test_day10_shadow_zombie.py`
- `tests/test_day17_bot_traffic.py`

Tests cover login behavior, valid/tampered/expired tokens, malformed authorization headers, legacy login-status behavior and credential-stuffing scenarios.

**Limitations:** These are selected authentication scenarios, not a comprehensive assessment. Historical credential-stuffing outcomes alone do not establish authentication security. Some stack-dependent tests were skipped.

### API3 — Broken Object Property Level Authorization (BOPLA)

**Status: PARTIAL**

Evidence: `tests/test_day25_pii_leakage.py` and `logs/pii_leakage_report.json`.

The historical Day 25 report completed with 202 findings. It tested selected profile and invoice exposure paths, including foreign and unauthenticated legacy invoice access. Log inspection found zero payload matches, and cleanup completed successfully.

**Limitations:** This demonstrates selected sensitive-data exposure paths, not comprehensive property-level read and write authorization. The 202 findings are not 202 distinct production vulnerabilities.


### API4 — Unrestricted Resource Consumption

**Status: PARTIAL**

Evidence:
- `tests/test_day17_bot_traffic.py`
- `tests/test_day18_rate_limiting.py`
- `logs/day18_20261031_120756/rate_limit_effectiveness_report_rerun.json`

The historical Day 18 report recorded `PASS`. It validated flood blocking, legitimate traffic, recovery and negative-control behavior.

**Limitations:** The report explicitly identifies the validation as a local integration test using a temporary mock limiter. It does not establish production capacity or protection against every resource-exhaustion vector.

### API5 — Broken Function Level Authorization

**Status: COVERED**

Evidence: `tests/test_day10_shadow_zombie.py`.

Tests cover the administrative reset-cache route, diagnostic and internal configuration routes, legacy endpoint exposure and authentication requirements on selected v2 endpoints.

**Limitations:** Coverage is limited to administrative and legacy routes implemented in the lab. Tests confirming intentionally exposed routes document weaknesses; they do not certify secure function-level access.

### API6 — Unrestricted Access to Sensitive Business Flows

**Status: OUT_OF_SCOPE**

The inspected lab does not expose a qualifying sensitive business workflow such as purchasing, payment transfer or a comparable high-impact business flow.

**Limitations:** This category was not tested. Out of scope does not mean the category is secure.

### API7 — Server Side Request Forgery (SSRF)

**Status: OUT_OF_SCOPE**

The inspected service source did not identify outbound URL-fetching functionality or an endpoint accepting a URL for server-side retrieval.

**Limitations:** No SSRF test scenario was run. This scope decision is not a general claim that SSRF is impossible.

### API8 — Security Misconfiguration

**Status: NOT_RUN**

No sufficient dedicated security-misconfiguration validation evidence was identified.

Source-level settings such as `debug=False` do not establish that runtime configuration, HTTP headers, TLS, CORS, error handling and deployment settings are secure.

**Limitations:** This category remains unverified and requires a dedicated configuration assessment.

### API9 — Improper Inventory Management

**Status: PARTIAL**

Evidence:
- `tests/test_day11_endpoint_scanner.py`
- `tests/test_day12_discovery_verification.py`
- `logs/discovery_verification_report.json`

Historical Day 12 verification:
- Verdict: `FAIL`
- Ground-truth endpoints: 7
- Matched endpoints: 6
- Precision: approximately 85.7%
- Recall: approximately 85.7%

**Limitations:** The historical verification missed one expected endpoint and included one false positive. It was historical mock verification, not a fresh live inventory scan.

### API10 — Unsafe Consumption of APIs

**Status: OUT_OF_SCOPE**

No third-party API consumption functionality was identified in the inspected lab services.

**Limitations:** No third-party API consumption security tests were run. Out of scope does not establish that external API responses would be consumed safely if integrations were added.

## 5. Coverage scoring

The runner uses this weighted coverage method:

| Category status | Weight |
|---|---:|
| `COVERED` | 1.0 |
| `PARTIAL` | 0.5 |
| `FAILED` | 0 |
| `BLOCKED` | 0 |
| `NOT_RUN` | 0 |
| `OUT_OF_SCOPE` | Excluded from denominator |

Formula:

    weighted coverage percentage =
        sum of in-scope category weights
        / number of in-scope categories
        * 100

This is a lab-specific reporting metric, not an OWASP score, security certification or measurement of production security.

## 6. Day 26 execution result

The recorded regression execution produced:

| Result | Count |
|---|---:|
| Passed | 124 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 2 |
| Deliberately deselected | 1 |

Category distribution:

| Status | Count |
|---|---:|
| `COVERED` | 2 |
| `PARTIAL` | 4 |
| `OUT_OF_SCOPE` | 3 |
| `NOT_RUN` | 1 |
| `BLOCKED` | 0 |
| `FAILED` | 0 |

Weighted in-scope coverage:
- In-scope categories: 7
- Weighted score: 4.0 out of 7
- Coverage percentage: **57.14%**
- Overall assessment: **PARTIAL**

Successful pytest execution does not convert partial, untested or out-of-scope categories into security passes.

## 7. Evidence handling and limitations

- Historical reports are read as evidence; they are not rerun or rewritten by the regression runner.
- The Day 25 live audit execution workflow is not invoked.
- The tracked Day 24 PII payload fixture is preserved.
- Skipped tests are reported separately and are not counted as passed.
- Missing or unreadable required historical evidence blocks the associated category.
- The JSON report is the machine-readable record of the regression run.
- This assessment is limited to the authorized local API-Sentinel lab.

## 8. Follow-up work

1. Add a dedicated API8 security-misconfiguration assessment.
2. Expand API3 tests to cover property-level read and write authorization.
3. Improve API9 discovery until all ground-truth endpoints are found without false positives.
4. Extend API2 and API4 validation beyond the selected scenarios.
5. Add business-flow, SSRF and third-party API tests if those capabilities are introduced into the lab.

---

**Day 26 conclusion:** The regression suite consolidates existing evidence and executes successfully. The result is a partial OWASP API Security Top 10 (2023) assessment with explicit limitations and out-of-scope categories. It does not claim complete coverage or production certification.
