# Rate Limiter / Bot Detection Interface Contract

**Purpose:** Define the interface Member 4's production rate-limiting
and bot-detection component must satisfy.

**Current implementation:** `scripts/rate_limiting/mock_rate_limiter.py`
is MOCK DATA — TEMPORARY. It is a test substitute, not the production
security control.

## 1. Architecture

The limiter must sit in front of the API-Sentinel services and accept
requests through a proxy, gateway middleware, or standalone service.

| Service | Upstream URL | Mock listener |
|---|---|---|
| Auth | `http://127.0.0.1:5001` | `http://127.0.0.1:7001` |
| User | `http://127.0.0.1:5002` | `http://127.0.0.1:7002` |
| Order | `http://127.0.0.1:5003` | `http://127.0.0.1:7003` |
| Billing | `http://127.0.0.1:5004` | `http://127.0.0.1:7004` |

The mock listeners run on the host and forward requests to the existing
host-published service ports.

## 2. Client identification

- Prefer the bearer token when a valid `Authorization: Bearer ...`
  header is present.
- Otherwise, identify the client by its source IP address.
- Never log raw bearer tokens in validation reports.
- Identity normalization and token hashing may be implemented by the
  production component, provided equivalent clients are treated
  consistently.

## 3. Required behavior

- Enforce a per-client sliding-window request limit.
- Default minimum test configuration: 20 requests per 5-second window.
- Requests within the configured limit are forwarded to the upstream.
- Requests exceeding the limit receive HTTP `429 Too Many Requests`.
- A rate-limit response must contain JSON with this shape:

  ```json
  {
    "error": "rate_limited",
    "retry_after_seconds": 5
  }
  ```

- `retry_after_seconds` must be a non-negative integer representing
  the estimated wait before retrying.
- Upstream responses must preserve the meaningful status and response
  body without forwarding inappropriate hop-by-hop headers.
- Upstream connection failures must not be misreported as rate-limit
  blocks.
- The limiter must recover after the client's sliding window expires;
  a single burst must not cause a permanent ban.

## 4. Day 18 validation requirements

The grading harness will evaluate:

1. Flood abuse: measure HTTP 429 responses against total completed
   requests, with transport errors reported separately.
2. Credential stuffing: measure throttling of repeated login attempts.
3. Legitimate traffic: target a pass rate of at least 95%.
4. Recovery: verify that the same client identity can make a request
   after the limiting window expires.
5. Negative control: an intentionally permissive configuration must
   fail the abuse-blocking threshold.
6. Reporting: save request counts, response categories, rates,
   thresholds, recovery status, and an overall PASS/FAIL verdict.

The mock's default grading target is at least 50% flood blocking,
at least 95% legitimate request success, and confirmed recovery.
These are test thresholds, not claims about production effectiveness.

## 5. Replacement procedure

When Member 4 supplies the real component:

1. Confirm its listener URLs and supported request methods.
2. Confirm that rate-limited requests return HTTP 429.
3. Update `TARGET_URLS` in
   `scripts/rate_limiting/rate_limit_validation.py`.
4. Configure authentication and upstream routing as required.
5. Re-run the unit, integration, positive, and negative tests.
6. Replace mock results in the Day 18 report with measurements from
   the real component.

The grading logic should remain independent of the mock implementation.
If the real component exposes different response semantics, document
and explicitly adapt the interface rather than silently treating
different responses as equivalent.

## 6. Scope and limitations

This contract defines a minimum validation interface, not a complete
production bot-detection specification. Distributed attacks, rotating
identities, endpoint-specific limits, shared state across replicas,
and persistence across restarts require separate design and testing.

All Day 18 attack simulations must remain within the authorized,
local API-Sentinel lab.

## 7. Mock storage failure policy

The temporary mock uses a fail-closed policy when rate-limit storage cannot
be opened or updated. It returns HTTP `503 Service Unavailable` with JSON
`{"error":"rate_limiter_unavailable"}` and `Retry-After: 1`. It must not
forward that request upstream. A storage failure is not counted as an HTTP
429 rate-limit decision.

SQLite transactions serialize updates to the shared sliding-window state.
Concurrency tests must verify that requests sharing an identity cannot
exceed the configured limit, and that distinct identities have independent
limits. This policy and these tests describe the mock; production behavior
must be verified separately.
