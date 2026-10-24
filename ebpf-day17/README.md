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
- The Python synchronizer is not yet connected to the FastAPI lifespan or to
  an existing heuristic verdict producer.
- Kernel map creation and packet enforcement are separate operations.
