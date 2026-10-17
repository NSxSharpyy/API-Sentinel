# Day 8 — Automated BOLA Attack Test Suite

## 1. Purpose

The BOLA attack harness tests object-level authorization in the local
API-Sentinel mock services. It records structured JSONL evidence for
cross-user access, own-object access, blocked requests, authentication
failures, and unexpected errors.

## 2. Safety scope

The harness is restricted to the local mock target using
`http://127.0.0.1` or `http://localhost`.

Do not weaken the target validation or run the harness against systems
you do not own or have explicit authorization to test.

## 3. Prerequisites

1. Run commands from `appsec-testing`.
2. Activate the project's Python virtual environment.
3. Start the local mock services.
4. Ensure the seeded customer, order, and invoice data is available.

## 4. Targeted test

Test a specific invoice ID with two requests:

```bash
python scripts/attacks/bola_attack.py \
  --mode targeted \
  --invoice-id 3 \
  --repeats 2
```

For a cross-user authorization test, select an invoice belonging to a
different seeded customer from the authenticated attacker. Verify the
object owner before interpreting the result.

## 5. Sweep test

Test a bounded range of invoice IDs:

```bash
python scripts/attacks/bola_attack.py \
  --mode sweep \
  --start-id 1 \
  --end-id 160
```

The script reports request counts grouped by verdict. In sweep mode, it also reports the number of cross-user invoices classified as `BOLA_SUCCESS` and lists up to ten sample invoice IDs and owner IDs.

## 6. Authorization control and nonexistent object

Include an order authorization control and a nonexistent invoice:

```bash
python scripts/attacks/bola_attack.py \
  --mode targeted \
  --invoice-id 3 \
  --order-control \
  --nonexistent-invoice-id 999999
```

The order service should reject cross-user object access. A nonexistent
invoice should return a not-found response.

## 7. Evidence output

By default, evidence is appended to:

`logs/bola_attack.jsonl`

To keep a run separate from the default evidence file:

```bash
python scripts/attacks/bola_attack.py \
  --mode targeted \
  --invoice-id 3 \
  --repeats 2 \
  --output-dir logs/day8-targeted
```

Each JSONL record includes `verdict` (also available as `label`), `attacker_id`, `invoice_id`, `status` (also available as `http_status`), `duration_ms`, the route, and the attack sequence. `owner_id` is also available as `actual_owner_id`; it is null when the response does not identify an owner. The `cross_user_access` flag is included when ownership can be determined.

Attack records use `traffic_label: ATTACK`. Logs are append-only; retain
existing evidence when conducting additional runs.

## 8. Verdict labels

- `BOLA_SUCCESS`: HTTP 200 response identifies an object owner different
  from the authenticated attacker.
- `OWN_DATA`: the object's owner matches the attacker.
- `BLOCKED`: the request receives HTTP 403 or 404.
- `AUTH_FAILED`: authentication fails.
- `ERROR`: an unexpected response or request error occurs.

A `BOLA_SUCCESS` verdict is evidence of cross-user access in the
intentionally vulnerable mock service. It should not be interpreted as
a finding about an unrelated production system.

## 9. Automated tests

Run the Day 8 tests:

```bash
pytest -v tests/test_day8_bola_attack.py
```

Run the complete regression suite:

```bash
pytest -q
```
