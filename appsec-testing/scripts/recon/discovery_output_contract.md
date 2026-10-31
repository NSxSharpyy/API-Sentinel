# Member 3 Discovery Engine — Output Contract

## Purpose

Define the machine-readable output required by the Day 12
Shadow and Zombie API Discovery Verification process.

## Required JSON structure

{
  "scan_timestamp": "2026-10-19T09:00:00Z",
  "findings": [
    {
      "service": "auth",
      "method": "GET",
      "path": "/debug/dump-tokens",
      "classification": "shadow",
      "confidence": 0.95
    }
  ]
}

## Field requirements

### Top-level fields

- `scan_timestamp`: required ISO 8601 timestamp string.
- `findings`: required JSON array. An empty array is structurally valid,
  but it fails discovery verification because it finds no ground-truth routes.

### Finding fields

- `service`: one of `auth`, `user`, `order`, `billing`.
- `method`: one of `GET`, `POST`, `PUT`, `DELETE`.
- `path`: absolute URL path beginning with `/`; do not include scheme,
  hostname, query string, or fragment.
- `classification`: one of `shadow`, `zombie`, `documented`, `unknown`.
- `confidence`: JSON number from 0.0 through 1.0, inclusive.

Every finding must include all five fields. A finding must not repeat
the same service, method, and path tuple within one report.

## Classification meanings

- `shadow`: an unexpected endpoint outside the intended API surface.
- `zombie`: a legacy endpoint with weaker controls than the intended API.
- `documented`: an expected, documented endpoint.
- `unknown`: discovered endpoint whose role is not yet established.

Classification labels do not replace ground-truth verification. A known
ground-truth endpoint reported under the wrong classification is a
classification error.

## Endpoint matching

Compare service, HTTP method, and path. The Day 12 ground-truth manifest
uses `/api/v1/orders/1` as the canonical representative of the parameterized
route `/api/v1/orders/<int:order_id>`. Do not treat every numeric order ID
as a separate ground-truth endpoint.

## Verification expectations

The verifier must report:

- Ground-truth endpoints found and missed.
- Endpoint recall.
- False positives and precision.
- Classification errors.
- Invalid records and duplicate findings.
- An overall PASS or FAIL result.

The verifier must not count a documented route as a true positive merely
because the discovery engine returned it.
