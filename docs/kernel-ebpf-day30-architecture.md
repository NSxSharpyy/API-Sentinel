# Day 30 — Kernel eBPF Architecture

## 1. Overview

API-Sentinel uses eBPF programs in the Linux kernel to observe TCP connection state changes, inspect IPv4/TCP packets, identify HTTP requests, and enforce an IPv4 blocklist.

The eBPF component is implemented in Rust using Aya and communicates with userspace through BPF maps and a ring buffer.

## 2. Kernel Programs

| Program | Type | Responsibility |
|---|---|---|
| api_sentinel_ebpf | Tracepoint | Observes TCP state changes |
| api_sentinel_tcp_v4_connect | Kprobe | Associates socket addresses with process TGIDs |
| api_sentinel_http_classifier | TC classifier | Inspects IPv4/TCP traffic, identifies HTTP requests, and enforces the blocklist |

## 3. BPF Maps

| Map | Type | Purpose |
|---|---|---|
| SOCKET_TGID | HashMap | Socket address to process TGID mapping |
| CLIENT_IDENTIFIERS | HashMap | IPv4 address to client ID mapping |
| BLOCKLIST | HashMap | IPv4 addresses selected for blocking |
| EVENTS | RingBuf | Transfers NetworkEvent records to userspace |
| EVENT_DROPS | PerCpuArray | Counts events that could not enter the ring buffer |
| BLOCKLIST_DROPS | PerCpuArray | Counts packets rejected by blocklist enforcement |

## 4. Event Data Contract

The shared `NetworkEvent` structure is defined in `api-sentinel-ebpf-common/src/lib.rs`.

It uses `#[repr(C)]` so kernel and userspace code can share a consistent memory layout.

Fields include:

- Process TGID and attribution status
- Address family and transport protocol
- TCP old and new states
- Source and destination ports
- Source and destination IPv4 addresses
- Client identifier
- Traffic direction
- Event type and HTTP method
- URI length and URI prefix

Event types:

- `1`: TCP state event
- `2`: HTTP request event

HTTP method identifiers range from `0` (unknown) to `7` (OPTIONS).

## 5. TCP Event Flow

1. The TCP connect kprobe reads the socket pointer and current process TGID.
2. The socket-to-TGID mapping is stored in `SOCKET_TGID`.
3. The TCP state tracepoint reads connection metadata.
4. The tracepoint looks up process attribution.
5. A `NetworkEvent` is submitted to `EVENTS`.
6. Failed ring-buffer submissions increment `EVENT_DROPS`.
7. Socket attribution is removed when the connection reaches TCP_CLOSE (state 7).

## 6. HTTP Inspection and Enforcement Flow

1. The TC classifier receives a packet.
2. It validates Ethernet IPv4 and the minimum IPv4 header.
3. It checks source and destination IPv4 addresses against `BLOCKLIST`.
4. A matching non-zero blocklist entry increments `BLOCKLIST_DROPS` and returns `TC_ACT_SHOT`.
5. Non-TCP IPv4 traffic continues without HTTP inspection.
6. TCP header length, IPv4 total length, packet length, and fragment flags are checked.
7. The first 64 bytes of TCP payload are inspected for a supported HTTP method and URI prefix.
8. The source IPv4 address is used to look up a client identifier.
9. An HTTP `NetworkEvent` is submitted to `EVENTS`.
10. The packet continues with `TC_ACT_PIPE`.

## 7. Traffic Direction

The current heuristic classifies traffic as:

- `1`: East-West — both IPv4 addresses are RFC1918 private addresses.
- `2`: North-South — exactly one address is RFC1918 private.
- `0`: Unknown / Other — neither address is private.

## 8. Safety and Limitations

- HTTP inspection is passive; it does not modify HTTP payloads.
- The parser inspects only a fixed 64-byte TCP payload prefix.
- IPv4 fragments are skipped; packet reassembly is not implemented.
- Only Ethernet IPv4 packets are inspected by the current classifier.
- The current private-address heuristic does not classify every special-use IPv4 range.
- Ring-buffer capacity is finite; dropped events are counted.
- Blocklist enforcement applies to IPv4 packets, not only HTTP traffic.
- The mock e-commerce services are intended for an authorized local lab and must not be exposed to public or untrusted networks.

## 9. Userspace Integration

Userspace is responsible for loading and attaching the eBPF programs, managing maps, consuming ring-buffer events, and supplying client identifiers and blocklist entries.

The shared event structure must remain compatible across kernel and userspace components. Any ABI change requires coordinated updates and integration testing.

## 10. Validation

Day 30 documentation is based on the current source implementation in:

- `api-sentinel-ebpf-ebpf/src/main.rs`
- `api-sentinel-ebpf-common/src/lib.rs`

Build and formatting validation should be performed before committing this documentation.
