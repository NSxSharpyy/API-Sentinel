# Day 11 — Endpoint Discovery Baseline

## Objective

Establish a black-box endpoint discovery baseline for the local API-Sentinel
lab. The scanner probes candidate paths, checks version siblings of known
public v2 routes, enumerates HTTP methods, and records its findings.

## Scope and methodology

The scanner targets four local services:

| Service | Base URL |
|---|---|
| Auth | `http://127.0.0.1:5001` |
| User | `http://127.0.0.1:5002` |
| Order | `http://127.0.0.1:5003` |
| Billing | `http://127.0.0.1:5004` |

The scan has three phases:

1. **Wordlist probing:** Send GET requests for each wordlist candidate to each
   service. Responses other than HTTP 404 are recorded as candidates.
2. **Version-sibling probing:** Derive and probe v1 and v3 siblings of known
   v2 route patterns. The scanner does not read the shadow/zombie manifest.
3. **Method enumeration:** Probe GET, POST, PUT, and DELETE for each candidate
   and classify the HTTP response.

A non-404 response is a discovery signal, not proof that a route is vulnerable.
HTTP 401 indicates authentication is required; it does not mean the route is
absent. HTTP 405 indicates the tested method is not allowed.

## Corrected discovery results

The corrected run used **33 wordlist candidates** and reported **4 candidate
endpoints**.

| Phase | Service | Candidate path | Observed GET response |
|---|---|---|---:|
| Wordlist | Auth | `/debug/dump-tokens` | 200 |
| Wordlist | User | `/internal/config` | 200 |
| Version sibling | Order | `/api/v1/orders/1` | 401 |
| Wordlist | Billing | `/_admin/reset-cache` | 405 |

These are the four candidates recorded by the corrected run. This result is
specific to the configured wordlist, known v2 patterns, services, and scan
behavior; it does not establish that no other undocumented endpoints exist.

## Method enumeration

| Candidate | GET | POST | PUT | DELETE |
|---|---:|---:|---:|---:|
| `auth/debug/dump-tokens` | 200 | 405 | 405 | 405 |
| `user/internal/config` | 200 | 405 | 405 | 405 |
| `order/api/v1/orders/1` | 401 | 405 | 405 | 405 |
| `billing/_admin/reset-cache` | 405 | 200 | 405 | 405 |

For `billing/_admin/reset-cache`, POST was the only enumerated method returning
HTTP 200. This establishes observed behavior in the lab, not the endpoint's
full impact or the safety of invoking the operation.

## Wordlist and provenance

The corrected wordlist contains 33 entries and no explicitly versioned
`api/v1/`, `api/v2/`, or `api/v3/` paths.

Three versioned paths had been manually checked before being added to the
earlier wordlist:

- Auth: `/api/v1/login-status` — previously observed HTTP 200
- User: `/api/v1/users/1` — previously observed HTTP 401
- Billing: `/api/v1/invoices/1` — previously observed HTTP 200

These three paths were removed from the wordlist before the corrected run.
They are historical observations, **not findings from the corrected run**,
and are not counted among its four candidates.

The order candidate `/api/v1/orders/1` was found by version-sibling probing
from the configured v2 order route pattern and returned HTTP 401.

## Evidence artifacts

Each scan writes:

- `logs/discovery_scan.jsonl` — individual probe records, including phase,
  service, path, method, status, and applicable classification.
- `logs/discovery_report.json` — timestamp, candidate count, candidates
  grouped by service, and method results grouped by endpoint.

The scanner replaces the JSONL log on each run. Copy the files elsewhere
before a new scan if you need to preserve historical evidence.

## Validation status

Validation results from the corrected run:

- Dedicated Day 11 scanner tests: `7 passed in 0.23s`
- Full test suite: `127 passed in 2.86s`
- `git diff --check`: no issues reported

These results describe the local environment at the time of validation.

## Limitations

- Non-404 responses can arise from catch-all routes and do not prove a
  meaningful endpoint exists.
- HTTP status alone does not establish response contents, authorization
  correctness, or security impact.
- Authentication-required responses can still indicate valid routes.
- Discovery coverage depends on the wordlist and configured version patterns.
- The corrected baseline does not compare findings with the shadow/zombie
  manifest; that comparison belongs to a later validation stage.
