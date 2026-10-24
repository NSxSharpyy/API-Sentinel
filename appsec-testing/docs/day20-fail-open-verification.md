# Day 20 — Fail-Open Mechanism Verification

## 1. Objective

Verify that legitimate application traffic can continue reaching the billing service when the simulated user-space enforcement component becomes unavailable.

The expected behavior is fail-open: when the test enforcer is unhealthy, the wrapper bypasses it and routes requests directly to the billing service.

## 2. Test architecture and scope

This verification uses an application-layer HTTP simulation:

- **Billing service:** `http://127.0.0.1:5004`
- **Day 20 test enforcer:** `http://127.0.0.1:8004`
- **Fail-open wrapper:** `http://127.0.0.1:8005`

When the test enforcer is healthy, the wrapper routes requests through it. The verification script then terminates only the test-enforcer process it started and checks whether the wrapper can route legitimate traffic directly to billing.

This is a simulation of fail-open routing. It is not proof that the actual TC/eBPF enforcement path automatically fails open when its user-space analysis daemon stops.

## 3. Verification procedure

1. Check that the billing service is healthy.
2. Start the Day 20 test enforcer.
3. Start the fail-open wrapper.
4. Send a legitimate request through the wrapper while the enforcer is healthy.
5. Confirm that the response indicates enforcement is active and that the test-enforcer header is present.
6. Terminate the test-enforcer process using `SIGKILL`.
7. Confirm that a subsequent legitimate request succeeds through the direct-to-billing bypass.
8. Confirm that the bypass response indicates enforcement is inactive and does not contain the test-enforcer header.
9. Check that the billing service remains healthy.
10. Clean up the processes started by the verification script.

## 4. Recorded results

The verification run completed with an overall result of `PASS`.

| Check | Result |
|---|---|
| Billing preflight | PASS — HTTP 200 |
| Test enforcer started | PASS |
| Wrapper started | PASS |
| Request through healthy enforcer | PASS — HTTP 200 |
| Request after enforcer termination | PASS — HTTP 200 |
| Billing remains healthy | PASS — HTTP 200 |

### Observed timings

- Legitimate request before enforcer failure: **25.31 ms**
- Fail-open recovery: **17.73 ms**

These timings are observations from one local simulation run, not general performance guarantees.

### Enforcer termination

- Method: `SIGKILL` through the verification script's subprocess handle
- Exit code: `-9`
- Target: Day 20 test-enforcer process only

The verification script also checks the response headers to distinguish enforced routing from direct bypass.

## 5. Evidence artifacts

The verification script writes its machine-readable report to:

`logs/fail_open_report.json`

Additional process logs:

- `logs/day20_test_enforcer.log`
- `logs/day20_fail_open_wrapper.log`

Automated regression tests:

`tests/test_day20_fail_open.py`

## 6. Automated validation

The following regression suites passed:

```bash
pytest -q tests/test_day20_fail_open.py
pytest -q tests/test_day19_kernel_drop.py tests/test_day20_fail_open.py
```

Results:

- Day 20 regression tests: **5 passed**
- Combined Day 19 and Day 20 regression tests: **26 passed**

The tests cover enforced routing, direct bypass routing, query-string preservation, upstream request failure handling, and wrapper health reporting.

## 7. Limitations and follow-up

The test enforcer is a simulated HTTP component. The actual Day 19 TC/eBPF classifier is not itself an HTTP proxy, and this test does not establish what happens to kernel-level enforcement when the real analysis daemon stops.

A separate integration test is required to establish the actual TC/eBPF failure behavior, including whether legitimate traffic remains available and whether security enforcement degrades as intended.

## 8. Conclusion

**Day 20 simulated fail-open verification: PASS.**

The local HTTP simulation demonstrates that the wrapper can route legitimate requests through the test enforcer while it is healthy and bypass it after the test-enforcer process terminates. The billing service remained healthy during the test.

This result is limited to the simulated application-layer wrapper and must not be reported as proof of fail-open behavior in the real TC/eBPF enforcement path.
