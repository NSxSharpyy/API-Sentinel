# Day 12: Shadow/Zombie API Discovery Verification

## Objective

Evaluate discovery output against the reconstructed ground-truth
manifest, checking endpoint coverage, false positives, classification
accuracy, and report validity.

## Ground truth and provenance

Ground truth is maintained in `docs/shadow_zombie_manifest.md`.

The manifest is explicitly marked as reconstructed from Day 10 tests,
the order service route implementation, and discovery-baseline
documentation. It is not claimed to be the recovered original manifest.

The Day 11 scan report is supplementary comparison evidence only.
It is not treated as ground truth.

## Output contract

Member 3's discovery output contract is defined in
`scripts/recon/discovery_output_contract.md`.

The expected report contains a scan timestamp and a findings array.
Each finding includes service, HTTP method, path, classification,
and confidence.

## Mock validation

The input `scripts/recon/mock_member3_discovery_output.json` is
intentionally imperfect test data. It is not real Member 3 engine output.

Expected mock results:

- Ground-truth endpoints: 7
- Valid unique findings: 7
- Correctly discovered ground-truth endpoints: 6
- Endpoint recall: 85.7%
- False positives: 1
- Precision: 85.7%
- Classification errors: 0
- Validation errors: 0
- Expected verifier result: FAIL, exit code 1

The missed endpoint is `user GET /api/v1/users/1`.
The unverified finding is `user GET /api/v2/users/me`, classified as
`unknown` rather than `documented`.

This negative result is expected and demonstrates that the verifier
rejects incomplete, noisy discovery output.

## Synthetic perfect-fixture validation

The synthetic fixture `logs/perfect_discovery_test.json` was verified
separately. It produced 7/7 ground-truth endpoints found, 100.0% recall,
100.0% precision, zero classification errors, and zero validation errors.
The verifier returned PASS and wrote
`logs/day12_perfect_fixture_verification.json`.

This confirms the verifier accepts a complete synthetic report; it is
not evidence that Member 3's real discovery engine has passed.

## Automated tests

Focused test command:

```bash
python -m pytest tests/test_day12_discovery_verification.py -v
```


Recorded focused test result: 16 passed.
Full regression command: `python -m pytest -q` — 153 passed.


## Interpretation and limitations

- The mock is controlled test data, not evidence of Member 3's actual
  discovery-engine performance.
- Day 11 scanner findings are comparison evidence only; they are not
  automatically accepted as true shadow or zombie endpoints.
- A perfect synthetic report tests the verifier's grading behavior;
  it does not establish real-engine 100% coverage.
- Ground-truth accuracy depends on the manifest and its supporting evidence.
- Parameterized endpoint paths must be compared consistently.

## Day 12 acceptance criteria

- [x] Reconstructed ground-truth manifest and provenance documented.
- [x] Member 3 output contract documented.
- [x] Imperfect mock includes a deliberate miss and a false positive.
- [x] Verifier reports metrics and exits nonzero for imperfect output.
- [x] Focused test suite passes (16 tests).
- [x] Full project regression suite passes (153 passed).
- [x] Imperfect mock fails with 6/7 endpoints found (85.7% recall).
- [x] Synthetic perfect fixture passes with 7/7 endpoints found (100% recall and precision).
- [ ] Final Git status and diff reviewed.
- [ ] Commit/push only after explicit authorization.
