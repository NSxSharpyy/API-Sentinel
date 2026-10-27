# API-Sentinel Day 17 — Blocklist Map Control

## Purpose

This module defines a separate IPv4 blocklist hash map and a userspace
utility for managing entries. It does not attach a packet-dropping program
and does not change the Day 16 packet-capture ring buffer.

## Map ABI

- Pin: /sys/fs/bpf/api_sentinel_day17_blocklist
- Name: api_sntl_bl17
- Type: BPF_MAP_TYPE_HASH
- Capacity: 4096 entries
- Key: 4 bytes, IPv4 address in network byte order
- Value: 8 bytes, CLOCK_MONOTONIC-compatible expiry in nanoseconds
- Expiry zero: permanent entry
- Expired entries: remain stored until explicitly removed

Any future eBPF enforcement program must use the same key and value ABI.
For temporary entries, it must compare the expiry with bpf_ktime_get_ns()
and treat an expired entry as not blocked. An expired entry is not
automatically deleted by this map definition.

The Python verdict adapter converts wall-clock expiration timestamps into
monotonic deadlines before updating the map.

## Utility

Build:

    make

Initialize the new map explicitly:

    sudo ./blocklist_map_ctl init

Add a temporary entry (TTL in seconds):

    sudo ./blocklist_map_ctl block 203.0.113.25 60

Add a permanent entry:

    sudo ./blocklist_map_ctl block 203.0.113.25 0

Inspect an entry:

    sudo ./blocklist_map_ctl show 203.0.113.25

Remove an entry:

    sudo ./blocklist_map_ctl unblock 203.0.113.25

The documentation-only address 203.0.113.25 is used in examples.

## Safety and current limitations

- The utility rejects loopback, unspecified, multicast, and limited-broadcast
  addresses.
- It refuses to use an existing pinned map with incompatible metadata.
- Initialization does not overwrite an existing pin.
- The map is state storage only. It cannot drop packets without a compatible
  eBPF program looking up this map and enforcing its entries.
- When `API_SENTINEL_BLOCKLIST_SYNC_ENABLED=1`, the FastAPI lifespan starts
  the map synchronizer and loopback-only verdict receiver.
- The receiver-to-worker-to-kernel-map path and opt-in lab BOLA policy are
  covered by tests. Packet-drop enforcement is separate and remains
  unverified until controlled runtime validation.
- A BOLA incident does not automatically create a block verdict. A separate,
  explicit policy decision is required.
- Kernel map creation and packet enforcement are separate operations.

## Experimental packet-drop enforcement

`blocklist_enforce.bpf.c` is a separate TC ingress classifier that consults
the existing Day 17 IPv4 hash map. It drops packets matching a permanent or
unexpired source-IP entry and passes missing or expired entries. It supports
Ethernet IPv4 with up to two VLAN tags.

Build only:

    make blocklist_enforce.bpf.o blocklist_enforcer_loader

Attachment requires both `API_SENTINEL_ENABLE_PACKET_DROP=1` and
`--enable-packet-drop`. The loader accepts only interface names starting
with `api-sntl-`; use a disposable test interface, never `eth0`, `lo`, or a
production interface. Ctrl+C requests detachment. If the process is forcibly
killed, inspect and detach the exact filter before proceeding.

Compilation is not runtime verification. Keep
`packet_drop_enforcement_configured: false` until controlled tests verify
matching packets drop, unrelated and expired-entry packets pass, and
detachment restores normal traffic.


## Day 19 — Blocked-packet audit stream

The enforcement program emits a record to the pinned ring buffer
`/sys/fs/bpf/api_sentinel_day17_drop_events` immediately before returning
`TC_ACT_SHOT`. The event includes the monotonic capture timestamp, ingress
interface index, attacker/source IPv4 address, target IPv4 address, TCP/UDP
ports when present, protocol, and the matched enforcement rule identifier.

Build the reader with:

    make blocklist_drop_reader

Build the updated enforcement object and loader before attaching the updated
program to a disposable `api-sntl-*` test interface. Follow the explicit
opt-in and detach procedure above. The application-side audit collector is
disabled by default; set `API_SENTINEL_BLOCKLIST_DROP_AUDIT_ENABLED=1` only
after the reader has been built and the drop-event map is pinned.

The audit rule identifier `day17.ipv4_source_blocklist` names the kernel
enforcement rule. It is not the originating heuristic rule ID: the existing
Day 17 blocklist map stores only expiration timestamps, not the original
verdict rule ID. A ring-buffer reservation failure does not allow a packet,
but means that particular packet's audit event could not be emitted.
