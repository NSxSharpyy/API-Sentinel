# Day 5 — Downstream HTTP Transaction Routing

Last audited: 2026-10-25

## Implemented contract

- `http.transaction` remains the backward-compatible per-message topic. It
  carries each parsed request or response as UTF-8 JSON, with HTTP fields and
  the body Base64-encoded.
- `discovery.http.transaction` carries one completed, correlated HTTP
  request/response pair for the Discovery consumer.
- `heuristics.http.transaction` carries the same completed transaction for the
  Heuristics consumer.
- The two downstream topics are emitted by `HTTPMessagePipeline` only after
  request/response correlation completes. Their JSON payload has
  `message_type: "completed_transaction"` with nested `request` and `response`
  objects and a normalized `connection_key`.
- Database persistence and downstream publication failures are logged
  independently; best-effort ZeroMQ publication does not provide a durable
  acknowledgement or prove consumer-side processing.

## Repository verification

- `tests/test_message_broker.py` checks the legacy topic and both downstream
  topics, including request/response pairing.
- `tests/test_http_pipeline.py` checks opposite-direction correlation and
  downstream publication of completed transactions.
- The full Python suite passed after the changes in the audit workspace.

## Acceptance boundary

**Partial until external acceptance.** Member 3 and Member 4 consumer
implementations/deployments are not present in this repository snapshot. The
producer's topic and payload contract can be verified here, but cross-repository
compatibility needs consumer contract tests or written confirmation from those
owners. PUB/SUB remains best-effort and non-durable; use a durable broker or an
acknowledged delivery design if lossless delivery is required.
