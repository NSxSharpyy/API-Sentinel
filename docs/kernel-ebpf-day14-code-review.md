# API-Sentinel Kernel eBPF — Day 14 Code Review

## 1. Scope

Reviewed the kernel eBPF packet classifier, shared NetworkEvent
definition, and userspace ring-buffer event handling.

This review covers the inspected source and recorded build/test results.
It is not a formal security audit or proof of production readiness.

## 2. Findings

### Shared event structure

- NetworkEvent is shared between the eBPF and userspace crates.
- The structure uses #[repr(C)] to provide a C-compatible field layout.
- Event fields include process attribution, IP addresses, ports,
  event type, HTTP method, traffic direction, and a URI prefix.
- Userspace checks the event length against size_of::<NetworkEvent>().
- Userspace uses read_unaligned to read the event from ring-buffer memory.

Status: Basic ABI handling looks reasonable. Automated ABI/layout tests
are not currently present.

### Userspace event processing

- HTTP request events and TCP state events have separate display paths.
- HTTP output includes method, client identifier, URI prefix, direction,
  and source/destination endpoints.
- TCP output distinguishes known process attribution from UNKNOWN.

Status: Inspected display and event-reading paths appear consistent with
the shared event structure. Automated event-decoding tests are absent.

### HTTP packet classifier

- Checks Ethernet and IPv4 packet structure before parsing.
- Validates IPv4 version, header length, and TCP protocol.
- Validates TCP header length before reading the payload.
- Checks declared IPv4 length and available packet data.
- Skips fragmented IPv4 packets.
- Recognizes common HTTP methods and origin-form paths beginning with '/'.
- Captures only a short URI prefix.
- Returns TC_ACT_PIPE, allowing traffic to continue.

Status: The inspected checks provide useful bounds validation for the
supported packet format. Further automated tests and runtime validation
are needed.

## 3. Known limitations

- No TCP stream reassembly; HTTP data split across TCP segments may be missed.
- HTTPS/TLS payloads are not decrypted or parsed as HTTP.
- IPv6 and VLAN-tagged Ethernet traffic are not supported by this parser.
- Requests with less than the configured 64-byte TCP payload read length
  may be skipped.
- Only a short URI prefix is retained, not the complete path.
- The private IPv4 address heuristic is not authoritative client identity.
- No automated unit tests currently exercise packet parsing or event ABI.

## 4. Build and test results

### Default cargo test

Command:
cargo test

Result: Passed. The userspace and shared crates reported zero tests.
This verifies that the default test targets completed, but does not
validate parser correctness.

### Shared crate tests

Command:
cargo test -p api-sentinel-ebpf-common

Result: Passed; zero tests were discovered.

### Full workspace tests

Command:
cargo test --workspace

Result: Failed while linking the eBPF binary as a host test executable,
with an undefined symbol: main error. The eBPF binary uses no_main,
so it needs an appropriate eBPF build/test workflow rather than being
treated as an ordinary host test executable.

### Build warning

Cargo reported that the workspace dependency clap is unused.
This is a warning, not a test failure.

## 5. Review conclusion

The inspected userspace ring-buffer length check and unaligned read are
sensible. The inspected packet parser includes multiple bounds checks
and passes traffic onward rather than blocking it.

However, zero automated tests means parsing correctness is not yet
demonstrated by tests. The full workspace test command also needs a
suitable eBPF-aware test/build strategy.

This review does not certify the implementation as production-ready.
Recommended follow-up: add tests for event layout and HTTP parsing,
and validate malformed, truncated, fragmented, and unsupported packets.

## 6. Repository state

Branch: kernel-ebpf

No implementation changes were made as part of this review report.
