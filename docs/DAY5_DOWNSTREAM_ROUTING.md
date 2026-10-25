# Day 5 — Downstream HTTP Event Routing

Last audited: 2026-10-25

## Implemented

The ZeroMQ publisher preserves the original `http.transaction` topic and also
publishes each complete parsed HTTP request/response message to:

- `discovery.http.transaction` — consumer route for the Discovery module.
- `heuristics.http.transaction` — consumer route for the Heuristics module.

`HTTPTransactionSubscriber` accepts one of the configured topics. The payload
is the existing UTF-8 JSON contract, including the message type, directional
connection ID, capture timestamp, HTTP fields and Base64-encoded body. Existing
consumers subscribed to `http.transaction` are not required to change.

## Verification

- Unit/runtime broker tests verify the legacy topic and each downstream route.
- The publisher and subscriber use ZeroMQ PUB/SUB, which is best-effort and
  non-durable. Consumers may miss events while disconnected or not subscribed.
- The Member 3/Member 4 services are not present in this repository snapshot;
  their deployment and semantic integration cannot be claimed as verified here.

## Acceptance status

**Partial.** Routing channels and tests are implemented. Cross-repository
consumer acceptance by Member 3 and Member 4 still needs confirmation.
