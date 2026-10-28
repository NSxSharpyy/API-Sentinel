# Mock E-Commerce Architecture (Day 1)

## Purpose
Intentionally vulnerable lab platform used ONLY to validate the eBPF API
security project. Never expose it outside the lab network.

## Services
| Service | Port | Responsibility |
|---|---|---|
| auth-service | 5001 | Login, token verification |
| user-service | 5002 | Customer profile |
| order-service | 5003 | Orders |
| billing-service | 5004 | Invoices/payments (BOLA target, Day 2) |

## Conventions
- API prefix: /api/v2/ (legacy /api/v1/ zombie routes injected Day 10)
- Every response carries an X-Request-ID header
- Every request is logged as one JSON line
- Errors are JSON only; no stack traces

## Planned vulnerabilities (documented, intentional)
- Day 2: BOLA on billing invoice lookup
- Day 10: Shadow debug endpoints, deprecated v1 routes

## Out of scope today
Containers (Day 2), database (Day 3), traffic generator (Day 4).
