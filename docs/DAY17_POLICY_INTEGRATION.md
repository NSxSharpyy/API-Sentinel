# Day 17 — BOLA Policy to Blocklist Verdict Integration

Date audited: 2026-10-25

## Status

**Policy-to-verdict-queue integration is verified in tests. Separate isolated
kernel packet-drop runtime tests are now confirmed. The combined live
detection-to-kernel-map-to-packet-drop sequence remains unverified, and the
FastAPI application does not automatically attach the enforcement program.**

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
  `packet_drop_enforcement_configured: false` until the deployed application's
  enforcement lifecycle (including its actual attachment state) is designed and
  verified. The standalone loader's existence does not mean it is attached.

## Additional verification recorded on 2026-10-25

### Policy-to-synchronizer integration regression test

A new `tests/test_blocklist_e2e.py` exercises the full software path through the
real loopback ZeroMQ sender and receiver, verdict validation, bounded queue,
`BlocklistSynchronizer`, and a recording map-writer adapter. It verifies that
a qualifying lab BOLA verdict reaches the map-writer boundary with the expected
source IP, action, rule ID, and expiry fields. This test uses an injected writer;
it does not modify the host kernel map.

### Isolated eBPF packet-drop runtime test

The developer subsequently ran the separate experimental TC classifier and
loader against a disposable veth pair and network namespace. The observed
results were:

1. Before inserting a blocklist entry, traffic from `198.18.0.2` to the test
   host replied successfully.
2. With a 45-second active map entry for `198.18.0.2`, ping received no replies
   (100% packet loss).
3. The unrelated source `198.18.0.6` continued to receive replies.
4. After waiting 46 seconds, the entry was reported expired and traffic from
   `198.18.0.2` again received replies.
5. Ctrl+C reported `Enforcement filter detached.` The ingress filter listing was
   empty, `bpftool net show` reported no attached TC programs, the temporary
   entry was removed, and the test interface/namespace were removed.

These observations verify the **isolated packet-drop program behavior** in the
user's WSL lab. They are separate from the Python test that uses a recording
map writer.

## Updated acceptance verdict

**Partial — policy, receiver, synchronizer boundary and isolated kernel
classifier are verified separately; the combined live detection-to-real-kernel
map-to-packet-drop sequence remains outstanding.** The FastAPI process does not
automatically attach the packet-drop classifier. The loader remains an explicit,
manual, opt-in lab operation on `api-sntl-*` interfaces. Keep
`packet_drop_enforcement_configured` false until the deployed application's
actual enforcement lifecycle is designed and verified. Do not attach this to
`eth0`, `lo`, or production interfaces.

## Integrated kernel packet-drop runtime test — 2026-10-25

Environment: WSL, Python 3.14, isolated disposable veth network.

- Baseline connectivity: both test sources passed before enforcement.
- Controlled BOLA incident: incident ID 1 persisted for source `198.18.0.2`.
- Policy: one verdict submitted, zero skipped and zero failures.
- Loopback receiver: one verdict accepted, zero rejected or malformed.
- Kernel synchronizer: one update applied, zero failures; observed apply latency
  was 0.359176 ms for this run.
- Pinned map: temporary block entry for `198.18.0.2` was present.
- Active verdict: traffic from `198.18.0.2` was dropped.
- Unrelated source: `198.18.0.6` traffic continued to pass.
- Expiry: traffic from `198.18.0.2` passed again after the 20-second TTL.
- Cleanup: filter detached, temporary entry absent, namespace and interface
  removed, and no network BPF attachments reported.

Result: controlled end-to-end lab test passed. This does not establish
sustained sub-millisecond latency, production readiness, or integration with
the normal FastAPI application lifecycle. Keep enforcement status and
configuration reporting conservative until those checks are complete.

## Application-lifecycle kernel enforcement test — 2026-10-25

Environment: WSL, Python 3.14, isolated veth network and disposable namespace.

- Baseline ping tests passed for both test sources before enforcement.
- Synthetic login and cross-owner invoice request traversed the real
  application pipeline.
- BOLA incident 1 was persisted for source `198.18.0.2`, with an endpoint
  record created.
- The policy submitted one verdict; the loopback receiver accepted one;
  the kernel synchronizer applied one update, with zero reported failures.
- The observed map-application latency was 0.404586 ms for this run.
- Active verdict dropped traffic from `198.18.0.2`; unrelated traffic from
  `198.18.0.6` continued to pass.
- Traffic from `198.18.0.2` passed again after the 20-second TTL.
- The enforcement filter detached, the test blocklist entry was absent,
  the test namespace/interface were removed, and `bpftool net show` reported
  no network BPF attachments.

Result: controlled end-to-end application-lifecycle test passed.
The single map-application measurement does not prove that end-to-end
detection-to-enforcement latency stays below 1 ms under sustained load.
Production readiness and broader performance acceptance remain outstanding.
