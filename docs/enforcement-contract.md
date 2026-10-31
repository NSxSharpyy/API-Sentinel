# API-Sentinel Enforcement Contract

## Purpose

Define falsifiable requirements for Active Enforcement Mode and distinguish application-layer rejection from packet dropping before an HTTP response.

## Enforcement outcomes

### Application-layer enforcement

An application-layer limiter may reject a request with HTTP 429. This proves that an HTTP-serving component returned a rate-limit response; it does not prove that the request was dropped before reaching the application.

Required evidence:
- The HTTP response status and associated request record.
- The applicable rate-limit policy and threshold.
- Legitimate-traffic and recovery checks where required by the test plan.

### Kernel-level enforcement

A kernel-level packet-drop claim requires evidence independent of an HTTP 429.

Required evidence:
- The intended TC/eBPF program was successfully loaded and attached.
- The controlled test traffic matched the intended classifier.
- The kernel counters recorded positive matched and dropped packet counts.
- The matched and dropped counts satisfy the test's declared assertion.
- The client received no HTTP response during the observation window.
- Cleanup was verified, with ambiguous attachment state treated as failure.

Packet counters measure packets, not unique HTTP requests. A client timeout alone does not establish that no request bytes reached the application.

## Gate requirements

A kernel-drop verification gate passes only if:
1. Preflight succeeds without overwriting an existing TC configuration.
2. Program loading and filter attachment succeed.
3. Counter output is readable and valid.
4. Matched and dropped counts are both positive and equal.
5. The client receives no HTTP response and the expected timeout is observed.
6. Cleanup succeeds and no unintended filter remains attached.

Any failed assertion, invalid evidence, or unsuccessful cleanup must produce a nonzero process exit status. An inconclusive observation is not a pass.

## Negative-control requirement

The verification suite must deliberately simulate a nonfunctional enforcer, such as zero matched and zero dropped packets while an HTTP response is received. The gate must reject this observation.

The negative-control test validates the decision logic. It does not replace the privileged integration experiment.

## Active Enforcement Mode acceptance

Active Enforcement Mode is accepted only when the responsible implementation provides:
- A documented enforcement point and explicit policy.
- A reproducible test procedure and machine-readable evidence.
- Positive enforcement evidence for the controlled test.
- A negative-control test demonstrating rejection of nonfunctional enforcement.
- Verified cleanup and a nonzero exit status on failure.
- Clear separation between observed facts and evidence limitations.

## Scope and limitations

The Day 19 loopback TC/eBPF experiment is a controlled lab demonstration. It does not establish hardware offload, production-network readiness, complete TCP stream inspection, or universal prevention of application-level access.
