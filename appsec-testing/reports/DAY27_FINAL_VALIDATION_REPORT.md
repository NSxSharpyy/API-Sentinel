# API-Sentinel — Day 27 Final Validation Report

## 1. Project Overview

**Project Name:** API-Sentinel  
**Module:** Shadow API and Zombie API Discovery  
**Validation Day:** Day 27 — Final Validation  
**Branch:** `shadow-api`  
**Validation Date:** 09 November 2026

API-Sentinel is a security testing project designed to discover and validate potentially undocumented, shadow, and zombie API endpoints.

The final validation evaluates the endpoint discovery scanner against a predefined ground-truth manifest.

## 2. Validation Objectives

- Validate endpoint discovery coverage.
- Verify shadow and zombie API classification.
- Measure precision and recall.
- Identify false-positive findings.
- Review scanner output and verification reports.
- Document the limitations of the current implementation.

## 3. Test Environment

| Component | Details |
|---|---|
| Operating System | Windows |
| Shell | PowerShell |
| Project Language | Python |
| Test Framework | pytest |
| Git Branch | shadow-api |
| Ground-Truth Manifest | docs/shadow_zombie_manifest.md |
| Scanner Output | logs/actual_discovery_output.json |
| Verification Report | logs/actual_discovery_verification.json |

## 4. Validation Results

| Metric | Result |
|---|---:|
| Ground-Truth Endpoints | 7 |
| Valid Unique Findings | 10 |
| Matched Endpoints | 7 |
| Endpoint Recall | 100% |
| Precision | 70% |
| False Positives | 3 |
| Classification Errors | 0 |
| Validation Errors | 0 |
| Missed Endpoints | 0 |
| Final Verdict | FAIL |

## 5. False-Positive / Unverified Findings

The following endpoints were discovered by the scanner but were not documented in the ground-truth manifest:

| Service | Method | Endpoint |
|---|---|---|
| billing | GET | /api/v1/billing/1 |
| user | GET | /api/v0/users/export |
| user | GET | /api/v1/debug/metrics |

These findings require additional validation before they can be considered confirmed shadow or zombie API endpoints.

## 6. Classification Validation

All seven ground-truth endpoints were discovered and classified correctly.

- Shadow API endpoints were correctly identified.
- Zombie API endpoints were correctly identified.
- No classification errors were reported.
- No ground-truth endpoints were missed.

## 7. Interpretation of Results

The scanner achieved 100% recall, indicating that all endpoints defined in the ground-truth manifest were discovered.

The precision score of 70% indicates that three out of ten findings were unverified against the manifest.

The current validation result is FAIL because the verification process reported three false-positive or unverified findings.

The result does not indicate that all three endpoints are necessarily invalid. They require further investigation and supporting evidence.

## 8. Limitations

- Validation is based on a predefined ground-truth manifest.
- Undocumented endpoints require independent confirmation.
- Scanner discovery does not independently establish exploitability.
- The verification report does not prove that all real-world shadow or zombie APIs have been identified.
- Further testing is needed to reduce false positives.

## 9. Evidence Artifacts

The following files were generated or reviewed during validation:

- `logs/actual_discovery_output.json`
- `logs/actual_discovery_verification.json`
- `logs/discovery_report.json`
- `logs/discovery_scan.jsonl`
- `logs/api_posture_gap_report.json`
- `logs/discovery_verification_report.json`

## 10. Conclusion

The Day 27 final validation confirms that API-Sentinel successfully discovered all seven endpoints present in the ground-truth manifest, achieving 100% recall with zero classification errors.

However, the scanner produced three additional unverified findings, resulting in 70% precision and a FAIL verdict.

The results demonstrate strong endpoint discovery coverage while highlighting the need for improved false-positive reduction and independent validation.

The validation results have been documented without modifying the ground-truth manifest or artificially adjusting the verification metrics.

**Final Status: FAIL — Further false-positive investigation is required.**
