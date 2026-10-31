# Day 19 — In-Kernel Packet Dropping Verification

**Date:** 2026-10-23
**Status:** Controlled packet-drop experiment passed; reproducible automation pending.

## Objective

Verify that a TC/eBPF classifier attached to loopback ingress can drop
selected HTTP traffic before it reaches the billing service, while unrelated
service traffic remains healthy.

## Test setup

- Interface: `lo`
- Enforcement: TC ingress classifier, software execution (`skip_hw`)
- BPF program: `day19_request_drop`
- Program ID observed during test: `449`
- Source TCP port: `50355`
- Destination TCP port: `5004`
- Target path prefix: `GET /api/v2/billing/invoices/`
- Target invoice: `3`
- Requester: Alice (`alice.anderson1`)
- Invoice owner: Bob (`bob.brown2`)

Authentication tokens were kept in memory and were not included in the
reported output.

## Baseline

Before attaching the classifier, Alice authenticated successfully and
requested Bob's invoice `3`.

Observed results:

- Alice and Bob resolved to distinct user IDs.
- The invoice belonged to Bob.
- The cross-user request returned HTTP 200.
- The response confirmed Bob as the invoice owner.

This reproduced the lab's intentional billing BOLA behavior.

## Kernel classifier results

The counter-backed BPF program was attached to `lo` ingress. The controlled
request used source port `50355` and destination port `5004`.

Observed BPF map values after the request:

| Counter | Value |
|---|---:|
| `seen` | 20 |
| `matched` | 5 |
| `dropped` | 5 |

The client timed out waiting for a response. No invoice-related entries
matched the selected patterns in the billing container logs queried for the
last 30 seconds.

These results support the conclusion that the classifier matched and dropped
packets associated with the controlled request before an HTTP response was
received.

### Evidence limitations

- The counters count packets, not distinct HTTP requests. Multiple matches
  can result from retransmissions.
- A client timeout alone does not prove packet dropping.
- The billing log check was limited to a short time window and selected
  patterns; it does not independently prove that no request bytes reached the
  application.
- This experiment used a temporary, hard-coded source port and path prefix.
  It is a controlled lab demonstration, not a production-ready enforcement
  policy.
- The classifier checks the HTTP prefix within one packet. It does not handle
  requests whose relevant prefix is split across TCP segments.
- The classifier was attached to loopback ingress in software; this test does
  not demonstrate hardware offload or a production network deployment.

## Health and cleanup

All four service health endpoints returned healthy responses while the filter
was attached:

- Auth — port 5001
- User — port 5002
- Order — port 5003
- Billing — port 5004

The temporary TC `clsact` qdisc was removed with:

`sudo tc qdisc del dev lo clsact`

After cleanup, loopback returned to `noqueue`, no ingress filter was shown,
and billing health remained healthy.

## Automation validation

After the controlled experiment, the project artifacts were added and
validated without making further kernel changes.

- The TC/eBPF runner and read-only preflight are maintained under
  `scripts/enforcement/`.
- The Day 19 unit suite reports 18 passing tests, including cleanup
  safeguards for ambiguous attachment state.
- The read-only preflight returned `PASS`.
- The runner dry-run returned `PREFLIGHT_ONLY` and confirmed that it would
  not attach a filter.
- The loopback interface remained at `noqueue`, with no ingress or egress
  filters listed; billing health remained healthy.

**Validation result and limitation:** The privileged end-to-end runner was
executed after the latest cleanup changes and returned `OBSERVED`. It compiled
and loaded the program, attached the filter, recorded 5 matched and 5 dropped
packets, and reported successful filter and qdisc cleanup. Post-run checks
confirmed no remaining ingress or egress filters, the loopback `noqueue`
state, healthy billing, and 18 passing Day 19 unit tests. Packet counters
represent packets rather than distinct requests, and a client timeout alone
does not prove that no request bytes reached the application. Ambiguous
attachment state still requires manual inspection.

## Conclusion

**Controlled packet-drop evidence obtained.** The BPF map recorded five
matches and five drops, and the client received no HTTP response. Service
health remained intact and the temporary filter was removed.

Day 19 should not be considered fully reproducible or production-ready until
the classifier, test harness, automated assertions, and evidence collection
are maintained as project artifacts and validated together.
