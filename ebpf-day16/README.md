# API-Sentinel Day 16 eBPF producer scaffold

This is an additive implementation scaffold. It does not edit the existing Python repository files.

## ABI

`api_sentinel_event.h` defines the event layout inferred from the installed
`api-sentinel-ring-reader-day16` disassembly: 36 bytes of fields followed by
1500 payload bytes (1536 bytes total). This is an inference and must be checked
against real reader output before treating capture as validated.

## What it captures

The TC classifier captures IPv4 TCP packets with non-empty payloads. It supports
Ethernet/VLAN packets and packet data beginning directly at IPv4 (for loopback).
IPv6 and fragmented IPv4 packets are ignored. Only attach it to `lo` for the
initial local BOLA lab.

## Build (inside WSL)

From this directory:

```bash
make
```

If that fails, do not load anything into the kernel; save the full compiler
output and inspect it first.

## Prepare bpffs and launch

First stop the API-Sentinel FastAPI backend so it doesn't repeatedly launch the
reader while the producer is being prepared. Then, from this directory:

```bash
mountpoint -q /sys/fs/bpf || sudo mount -t bpf bpf /sys/fs/bpf
sudo ./loader ./packet_capture.bpf.o lo
```

Leave the producer running. It pins its ring buffer at
`/sys/fs/bpf/api_sentinel_day16_events`, matching the current `app/main.py`
reader argument. Start the FastAPI backend in a second terminal and inspect
`/queue-status` plus backend logs. Test traffic should remain on `127.0.0.1`.

## Stop / cleanup order

1. Stop the FastAPI backend first (Ctrl+C in its terminal).
2. Stop the producer (Ctrl+C in the loader terminal). It detaches its TC
   program and unpins the map.

The loader refuses to overwrite an existing pinned map. If startup fails, don't
remove a pin blindly; inspect `sudo bpftool map show`, the loader error, and the
reader/backend logs first.

## Limitations / acceptance

This is a first producer iteration, not proof that Day 16 is complete. WSL may
reject TC attachment or the loopback receive path may differ from the assumed
packet layout. Confirm compiler success, loader attachment, JSON reader events,
accepted packet counters, HTTP transaction parsing, and finally capture-to-
*detection* latency using the local BOLA scenario. Current capture-to-publish
telemetry alone is not capture-to-detection latency.
