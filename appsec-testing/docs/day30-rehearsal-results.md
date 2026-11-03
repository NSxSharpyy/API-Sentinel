# Day 30 — Live Demo Rehearsal Results

**Rehearsal date:** 3 November 2026
**Requested rehearsals:** 3
**Completed rehearsals:** 3
**Overall result:** PARTIAL

## 1. Executive Summary

Three non-interactive rehearsals of the eight-segment API-Sentinel demonstration
were completed successfully.

Each rehearsal recorded:
- 7 segments with PASS status
- 1 segment with PARTIAL status
- 0 failed segments
- 0 blocked segments
- 0 skipped segments

The PARTIAL result came from the OWASP API regression coverage classification.
It was consistent across all three runs and was not caused by a flaky live
demonstration segment.

All eight segments completed within their configured time budgets.

## 2. Rehearsal Run Results

| Run | Run ID | Overall | PASS | PARTIAL | FAIL |
|---|---|---|---:|---:|---:|
| 1 | `20261103T193016_run1_9e5235d4` | PARTIAL | 7 | 1 | 0 |
| 2 | `20261103T193043_run2_fe5bb873` | PARTIAL | 7 | 1 | 0 |
| 3 | `20261103T193108_run3_3e91084d` | PARTIAL | 7 | 1 | 0 |

## 3. Segment Timing and Reliability

All durations are measured execution times in seconds.

| Segment | Run 1 | Run 2 | Run 3 | Result |
|---|---:|---:|---:|---|
| Platform health | 0.024 | 0.086 | 0.023 | PASS in all runs |
| Manual BOLA | 1.865 | 1.935 | 2.035 | PASS in all runs |
| Automated BOLA | 1.067 | 1.262 | 1.174 | PASS in all runs |
| Real-time detection | 4.270 | 1.521 | 1.470 | PASS in all runs |
| Kernel evidence review | 0.002 | 0.001 | 0.000 | PASS in all runs |
| Fail-open verification | 7.456 | 7.366 | 7.457 | PASS in all runs |
| OWASP regression | 12.125 | 12.554 | 13.137 | PARTIAL in all runs |
| Report compilation | 0.162 | 0.141 | 0.110 | PASS in all runs |

### Total measured execution time

| Run | Total |
|---|---:|
| Run 1 | 26.971 seconds |
| Run 2 | 24.866 seconds |
| Run 3 | 25.406 seconds |
| **Average** | **25.748 seconds** |

No segment exceeded its configured budget. The measured execution time
excludes any separate presentation, narration, or manual operator activity.

## 4. BOLA Demonstration Results

The automated sweep used invoice IDs 1–50.

| Run | Confirmed cross-user BOLA successes |
|---|---:|
| Run 1 | 48 |
| Run 2 | 48 |
| Run 3 | 48 |

The counts were calculated from each run's own JSONL evidence. A finding was
counted only when its label was `BOLA_SUCCESS` and `cross_user_access` was
true.

The observed count was consistent across all three rehearsals. The count is
an experimental result, not a hardcoded pass criterion.

## 5. Real-Time Detection

The Day 16 detection runner passed in all three rehearsals.

The demonstration uses the explicitly labelled mock detection engine.
Its result demonstrates the configured lab detection workflow; it is not
evidence of a production detection deployment.

## 6. Enforcement and Fail-Open Evidence

### Day 23 kernel-drop evidence

The recorded Day 23 evidence passed the rehearsal checks in all three runs.

The evidence is qualified as a controlled TC/eBPF packet-drop test on the
loopback interface (`lo`), using destination port 5084. It does not establish
production network reliability or enforcement on the billing service port.

### Day 20 fail-open verification

The Day 20 fail-open verification passed in all three rehearsals.

This is an application-layer HTTP simulation. It must not be represented as
proof of kernel-level fail-open behavior.

## 7. OWASP Regression Coverage

The OWASP regression segment returned `PARTIAL` in all three rehearsals.

| Classification | Count |
|---|---:|
| COVERED | 2 |
| PARTIAL | 4 |
| FAILED | 0 |
| BLOCKED | 0 |
| NOT_RUN | 1 |
| OUT_OF_SCOPE | 3 |

The weighted in-scope score was:

- Earned score: 4.0
- Maximum score: 7
- Coverage: 57.14%

The score uses the regression runner's method:
- COVERED = 1
- PARTIAL = 0.5
- FAILED, BLOCKED, and NOT_RUN = 0
- OUT_OF_SCOPE categories are excluded from the denominator

This is a lab-specific regression coverage metric, not an OWASP certification.
PARTIAL and NOT_RUN categories are not counted as fully covered.

## 8. Reliability Assessment

Across the three rehearsals:

- All three runs completed all eight segments.
- No segment was skipped, blocked, or marked failed.
- All segments stayed within their configured time budgets.
- Automated BOLA results were consistent at 48 confirmed findings per run.
- Real-time detection passed in all three runs.
- The same OWASP coverage limitation appeared in every run.
- No intermittent segment failure was observed.

The rehearsal is therefore repeatable for the tested lab environment, with
the overall status remaining PARTIAL because of the OWASP coverage result.

## 9. Evidence Locations

Summary:

`appsec-testing/logs/day30_rehearsals/day30_rehearsal_summary_20261103T193133.json`

Run 1:

`appsec-testing/logs/day30_rehearsals/20261103T193016_run1_9e5235d4/`

Run 2:

`appsec-testing/logs/day30_rehearsals/20261103T193043_run2_fe5bb873/`

Run 3:

`appsec-testing/logs/day30_rehearsals/20261103T193108_run3_3e91084d/`

Each run directory contains its rehearsal report and segment-specific evidence.

## 10. Conclusion

The Day 30 eight-segment demonstration completed three consecutive rehearsals
without a failed or skipped segment. The live demonstration workflows were
repeatable and remained within their allocated time budgets.

The final rehearsal status is **PARTIAL**, not PASS, because the OWASP
regression runner classified its coverage as PARTIAL. This limitation is
recorded transparently and does not invalidate the successful execution of
the other seven segments.

The next validation step is the full AppSec regression test suite.
