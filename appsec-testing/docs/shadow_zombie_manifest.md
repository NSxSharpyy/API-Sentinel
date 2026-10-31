# Shadow and Zombie API Manifest

**Status:** Reconstructed ground-truth manifest
**Purpose:** Day 12 discovery-engine verification
**Provenance:** Reconstructed from `tests/test_day10_shadow_zombie.py`,
`services/order_service/app.py`, and `docs/discovery-baseline.md`.
This is not claimed to be the recovered original manifest.

## Ground-truth endpoints

| Service | Method | Path | Category | Evidence |
|---|---|---|---|---|
| auth | GET | /debug/dump-tokens | shadow | Day 10 unauthenticated-access test |
| auth | GET | /api/v1/login-status | zombie | Day 10 malformed-token test |
| user | GET | /internal/config | shadow | Day 10 unauthenticated-access test |
| user | GET | /api/v1/users/1 | zombie | Day 10 cross-user lookup test |
| order | GET | /api/v1/orders/1 | zombie | Day 11 version-sibling discovery; Day 10 tests the same parameterized route with ID 101 |
| billing | POST | /_admin/reset-cache | shadow | Day 10 POST test |
| billing | GET | /api/v1/invoices/1 | zombie | Day 10 unauthenticated invoice test |

## Classification notes

- **Shadow:** An intentionally injected endpoint outside the expected versioned API surface.
- **Zombie:** A legacy versioned endpoint with weaker controls than the intended API.
- The order endpoint is parameterized as `/api/v1/orders/<int:order_id>`.
  The `/1` path above is the canonical representative used in the Day 11 scan.
- This manifest contains seven ground-truth endpoint entries. The verifier
  must compare service, HTTP method, and normalized endpoint path, not path alone.
- Day 11 scanner output is independent discovery evidence, not ground truth.
  Additional scan results must not automatically be classified as shadow or zombie.
