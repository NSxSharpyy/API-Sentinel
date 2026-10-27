#ifndef API_SENTINEL_DAY19_DROP_EVENT_H
#define API_SENTINEL_DAY19_DROP_EVENT_H

#include <linux/types.h>

#define API_SENTINEL_DROP_EVENTS_PIN \
    "/sys/fs/bpf/api_sentinel_day17_drop_events"
#define API_SENTINEL_DROP_RULE_ID 1U
#define API_SENTINEL_DROP_RULE_NAME "day17.ipv4_source_blocklist"

/*
 * Captured at the actual TC_ACT_SHOT decision.
 * IPv4 fields remain in network byte order; ports are host byte order.
 */
struct api_sentinel_drop_event {
    __u64 captured_at_ns;
    __u32 interface_index;
    __u32 source_ip;
    __u32 destination_ip;
    __u16 source_port;
    __u16 destination_port;
    __u8 protocol;
    __u8 reserved[3];
    __u32 rule_id;
};

#if !defined(__BPF__)
_Static_assert(sizeof(struct api_sentinel_drop_event) == 32,
               "Day 19 drop event ABI size mismatch");
#endif

#endif
