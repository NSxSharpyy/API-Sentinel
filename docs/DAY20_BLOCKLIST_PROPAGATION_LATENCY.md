# Day 20 — Blocklist Map Update Latency

## Objective
Measure userspace-to-kernel BPF map update latency against the 1 ms target.

## Implementation
- Added a dedicated `BLOCKLIST` hash map to the eBPF program.
- Added a userspace test insertion using the reserved TEST-NET IPv4 address `192.0.2.20`.
- Measured the elapsed time for one map insertion.
- Read the inserted value back to verify the map update.

## Measured Result
- Measured insertion latency: 149.383 microseconds
- Target: less than 1,000 microseconds (1 ms)
- Single-insertion result: UNDER_1MS
- Read-back verification: PASS

## Limitations
- This is a single insertion measurement, not a repeated statistical benchmark.
- The classifier does not yet consult `BLOCKLIST` to drop matching packets.
- The measurement covers the userspace map insertion call, not end-to-end packet-blocking propagation.

## Conclusion
The measured map insertion completed within the 1 ms target in this run. Further repeated measurements would be needed to characterize latency consistency.
