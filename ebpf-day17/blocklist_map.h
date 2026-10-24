#ifndef API_SENTINEL_DAY17_BLOCKLIST_MAP_H
#define API_SENTINEL_DAY17_BLOCKLIST_MAP_H

#include <linux/types.h>

#define API_SENTINEL_BLOCKLIST_PIN \
    "/sys/fs/bpf/api_sentinel_day17_blocklist"

#define API_SENTINEL_BLOCKLIST_MAP_NAME "api_sntl_bl17"
#define API_SENTINEL_BLOCKLIST_MAX_ENTRIES 4096U

/*
 * Key: IPv4 address bytes in network order.
 * Value: CLOCK_MONOTONIC-compatible expiry timestamp in nanoseconds.
 * An expiry value of zero represents a permanent entry.
 */
struct api_sentinel_blocklist_value {
    __u64 expires_at_mono_ns;
};

_Static_assert(sizeof(__u32) == 4, "IPv4 map key must be 4 bytes");
_Static_assert(
    sizeof(struct api_sentinel_blocklist_value) == 8,
    "Blocklist map value must be 8 bytes"
);

#endif
