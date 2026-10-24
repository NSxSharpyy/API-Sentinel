#ifndef API_SENTINEL_EVENT_H
#define API_SENTINEL_EVENT_H

#include <linux/types.h>

/*
 * ABI reconstructed from the installed api-sentinel-ring-reader-day16
 * callback. Keep offsets stable: the reader consumes this exact layout.
 *
 *   0x00 u64 captured_at_ns (CLOCK_MONOTONIC-compatible kernel time)
 *   0x08 u32 packet_length
 *   0x0c u32 interface_index
 *   0x10 u32 source IPv4 address (stored in network-byte order)
 *   0x14 u32 destination IPv4 address (stored in network-byte order)
 *   0x18 u32 TCP sequence number (host-byte order)
 *   0x1c u16 source port (host-byte order)
 *   0x1e u16 destination port (host-byte order)
 *   0x20 u16 TCP payload length
 *   0x22 u8 protocol (6 = TCP)
 *   0x23 u8 TCP flags
 *   0x24 u8 payload[1500]
 *
 * Total size is 1536 bytes. The existing reader rejects records whose size
 * is <= 1535 bytes. Layout inferred from disassembly; validate in the lab.
 */
#define API_SENTINEL_MAX_PAYLOAD 1500
#define API_SENTINEL_EVENT_SIZE 1536

struct api_sentinel_event {
    __u64 captured_at_ns;
    __u32 packet_length;
    __u32 interface_index;
    __u32 source_ip;
    __u32 destination_ip;
    __u32 sequence_number;
    __u16 source_port;
    __u16 destination_port;
    __u16 payload_length;
    __u8 protocol;
    __u8 tcp_flags;
    __u8 payload[API_SENTINEL_MAX_PAYLOAD];
};

#if !defined(__BPF__)
_Static_assert(sizeof(struct api_sentinel_event) == API_SENTINEL_EVENT_SIZE,
               "API-Sentinel event ABI size mismatch");
_Static_assert(__builtin_offsetof(struct api_sentinel_event, payload) == 36,
               "API-Sentinel payload offset mismatch");
#endif

#endif
