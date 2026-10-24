# Day 17 — BOLA Policy to Blocklist Verdict Integration

Date audited: 2026-10-25

## Status

**Policy-to-verdict-queue integration verified in tests. Kernel packet-drop
enforcement is not verified and remains disabled.**

## Implemented path

- `TransactionStore` invokes the attached policy only for a detected outcome,
  after the transaction commit and alert publication.
- Policy evaluation is narrowly scoped to the lab BOLA incident title, high
  severity, a positive incident ID, and a valid IPv4 source address.
- A block verdict is sent only when that exact source IP is in the explicit
  allowlist. Non-detections, unrelated incidents, and non-allowlisted sources
  do not produce a block verdict.
- The policy is opt-in. Both `API_SENTINEL_BLOCKLIST_POLICY_ENABLED=1` and
  `API_SENTINEL_BLOCKLIST_SYNC_ENABLED=1` are required.
- `API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS` must contain explicit IPv4
  addresses, separated by commas. CIDR ranges and wildcard entries are not
  accepted. Loopback, unspecified, multicast, and limited-broadcast addresses
  are rejected.
- Verdict TTL defaults to 60 seconds and is bounded to 1–3600 seconds by
  `API_SENTINEL_BLOCKLIST_VERDICT_TTL_SECONDS`.
- `ThreadOwnedVerdictSender` owns the persistent synchronous ZeroMQ sender on
  one dedicated thread, avoiding socket use from multiple threads.
- Policy evaluation errors are caught after commit so they do not turn an
  already-persisted transaction into a failed persistence operation.
- Shutdown drains persistence before stopping verdict intake and
  synchronization, allowing pending policy sends to reach the receiver.
  The receiver-drain wait is bounded, and a timeout is logged.

## Verification evidence

- Real loopback policy-to-queue test: passed (1 test).
- The test exercised `BlocklistPolicy`, the thread-owned sender, the real
  `BlocklistVerdictSender`, the real loopback receiver, verdict validation,
  and queue acceptance.
- The test asserted the canonical verdict ID, block action, source IP,
  rule ID, and 60-second TTL. It used `203.0.113.25`, a documentation-range
  test address.
- Full test suite: 187 passed; 1 Starlette deprecation warning.
- The full-suite run is the test evidence recorded at the time of this report.

## Safety boundaries and remaining work

- The current BOLA detector identifies a lab heuristic; that signal alone is
  not production-grade proof of an attack.
- ZeroMQ send success alone does not prove the receiver accepted a verdict.
  The integration test separately observed receiver acceptance and queueing.
- Queue acceptance does not by itself prove that a kernel map update completed.
- Updating the kernel map does not itself drop packets.
- `/blocklist-status` must continue to report
  `packet_drop_enforcement_configured: false` until a compatible packet-drop
  enforcement program is separately implemented and tested.
- This test does not demonstrate packet dropping or production-safe blocking.
