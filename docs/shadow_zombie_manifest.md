# Shadow & Zombie API Manifest (Day 10)

**Purpose:** Ground truth for Day 12 discovery-engine verification.

This file is intentionally separate from the official architecture documentation.
Do not provide it to the discovery-engine operator before their scan.

## Shadow APIs

| Service | Method | Path | Authentication | Risk pattern |
|---|---|---|---|---|
| auth-service | GET | /debug/dump-tokens | None | Diagnostic information disclosure |
| user-service | GET | /internal/config | None | Internal configuration and feature-flag disclosure |
| user-service | GET | /api/v1/debug/metrics | None | Undocumented synthetic debug metrics |
| billing-service | POST | /_admin/reset-cache | None | Unauthenticated state-changing admin-style action |

## Zombie APIs

| Service | Method | Path | Authentication compared with v2 | Vulnerability |
|---|---|---|---|---|
| auth-service | GET | /api/v1/login-status | Weak dotted-string check using X-Auth-Token | False login-status result for malformed tokens |
| user-service | GET | /api/v1/users/<id> | Valid token required | Missing object ownership check |
| order-service | GET | /api/v1/orders/<id> | Any non-empty Authorization header | Authentication bypass and cross-user object disclosure |
| billing-service | GET | /api/v1/invoices/<id> | No authentication required | Unauthenticated invoice disclosure; BOLA also remains in v2 |
| billing-service | GET | /api/v1/billing/<id> | Valid token required | Missing object-level authorization check |
| user-service | GET | /api/v0/users/export | None | Deprecated synthetic export endpoint |

## Day 12 verification checklist

- [ ] Discovery engine finds all 4 shadow endpoints.
- [ ] Discovery engine flags all 6 legacy/deprecated zombie routes, including the v0 export route.
- [ ] Discovery engine does not misclassify documented v2 routes as shadow or zombie.
- [ ] Each finding is supported by evidence from the scan.

## Lab safety

These endpoints are intentionally vulnerable test fixtures. Keep the platform
isolated to the local lab and do not expose it to untrusted networks.

The reset-cache endpoint only increments an in-memory counter. It does not
delete database records or perform a destructive operation.
