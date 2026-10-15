# API-Sentinel Kernel/eBPF Phase 1 Review

## Status
Under review — Phase 1 freeze is not yet confirmed.

## Implemented
- TCP socket lifecycle tracing using sock:inet_sock_set_state.
- IPv4 TCP event filtering.
- Socket-to-TGID association using a BPF hash map.
- Structured NetworkEvent shared between eBPF and userspace.
- 16 MiB BPF Ring Buffer for kernel-to-userspace event transfer.
- AsyncFd-based userspace event reader.
- TCP state, source/destination IPv4 address, port and
  process-attribution status reporting.

## Validation Completed
- cargo fmt --all
- git diff --check
- cargo build
- HTTP and HTTPS test traffic generated network events.
- A 10-second idle check showed no change in run counters.
- Ring Buffer events were received and printed by the userspace
  loader.

## Preliminary Runtime Measurement
During a 10-request HTTPS test:
- Wall-clock time: approximately 8.90 seconds.
- Tracepoint runtime delta: 1,562,155 ns across 50 additional runs.
- Kprobe runtime delta: 38,869 ns across 10 additional runs.
- Combined measured program runtime delta: 1,601,024 ns.

These figures are preliminary and do not independently prove
the complete kernel CPU utilization target of below 2%.

## Known Gaps
- Raw TCP payload extraction is not implemented.
- Integration with Member 2's Python ingestion service has not
  been verified in this checkout.
- Ring Buffer output failures are currently ignored; dropped
  event counting is not implemented.
- Process attribution can be unknown when a socket is missing
  from the attribution map.
- The installed bpftool does not support the requested
  hardware-counter profiling command.

## Freeze Decision
Do not mark the complete Phase 1 engine as frozen until the team
reviews the missing payload-capture and ingestion requirements,
validates performance under representative traffic, and agrees
on any scope adjustments.
