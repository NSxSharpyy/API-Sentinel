# Mock E-Commerce Architecture (Day 2)

## Purpose

API-Sentinel uses an intentionally vulnerable mock e-commerce platform
to validate API security monitoring and authorization controls for the
eBPF API security project. Use only in an authorized local lab. Never
expose the intentionally vulnerable services to public or untrusted
networks.

## Services

| Service | Port | Responsibility |
|---|---:|---|
| auth-service | 5001 | Login and HMAC bearer-token verification |
| user-service | 5002 | Authenticated customer profile |
| order-service | 5003 | Authenticated, ownership-checked order access |
| billing-service | 5004 | Invoice access; intentionally vulnerable BOLA target |

## Authentication and Authorization

- Login issues HMAC-SHA256 signed bearer tokens with an expiration time.
- Protected endpoints reject missing, malformed, invalid, or expired tokens.
- User profile responses omit password hashes.
- Order lookup checks that the authenticated user owns the requested order.
- Billing invoice lookup intentionally omits the invoice ownership check
  to demonstrate Broken Object Level Authorization (BOLA).
- The Billing BOLA weakness is documented in `docs/vulnerabilities.md`.

## API Conventions

- API prefix: `/api/v2/`
- Legacy `/api/v1/` zombie routes are planned for Day 10.
- Every response carries an `X-Request-ID` header.
- Requests are logged as JSON lines, including the authenticated user ID
  where available.
- Billing logs include invoice ID, requester ID, owner ID, and a
  cross-user-access ground-truth flag.
- Errors use JSON responses without exposing stack traces.

## Container Deployment

- Docker Compose runs each service in its own container.
- Host ports are bound to `127.0.0.1` only.
- Containers run as a non-root application user.
- Health checks use each service's `/health` endpoint.
- Each service has its own Docker build context and dependencies.
- Start the lab from the repository root with `sudo docker compose up -d`.
- Check container status with `sudo docker compose ps`.
- Stop the lab with `sudo docker compose down`.

## Planned and Intentional Vulnerabilities

- Day 2: BOLA on Billing invoice lookup.
- Day 10: Shadow debug endpoints and deprecated v1 routes.

## Out of Scope

- Day 3: Persistent customer database.
- Day 4: Traffic generator.
