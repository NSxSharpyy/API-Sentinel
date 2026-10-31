
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

#define TEST_PORT 5084
#define SOURCE_PORT_MAP_SIZE 256

struct day23_stats {
    __u64 seen;
    __u64 matched;
    __u64 dropped;
};

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct day23_stats);
} day23_stats_map SEC(".maps");

/* One entry per source port that generated a matching SYN. */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, SOURCE_PORT_MAP_SIZE);
    __type(key, __u32);
    __type(value, __u64);
} source_port_hits SEC(".maps");

SEC("classifier")
int day23_concurrent_syn_drop(struct __sk_buff *skb)
{
    unsigned char ip[20];
    unsigned char tcp[20];

    const __u32 ip_offset = 14;
    __u32 key = 0;

    struct day23_stats *stats =
        bpf_map_lookup_elem(&day23_stats_map, &key);

    if (!stats)
        return 0;

    __sync_fetch_and_add(&stats->seen, 1);

    if (bpf_skb_load_bytes(skb, ip_offset, ip, sizeof(ip)) < 0)
        return 0;

    if ((ip[0] >> 4) != 4 || ip[9] != 6 || (ip[0] & 15) < 5)
        return 0;

    __u32 ip_header_len = (ip[0] & 15) * 4;
    __u32 tcp_offset = ip_offset + ip_header_len;

    if (bpf_skb_load_bytes(skb, tcp_offset, tcp, sizeof(tcp)) < 0)
        return 0;

    __u16 source_port = ((__u16)tcp[0] << 8) | tcp[1];
    __u16 destination_port = ((__u16)tcp[2] << 8) | tcp[3];

    if (destination_port != TEST_PORT)
        return 0;

    /* Match an initial SYN, not SYN-ACK or other TCP traffic. */
    if ((tcp[13] & 0x12) != 0x02)
        return 0;

    /*
     * Record each matching source port.
     * Retransmissions increment the existing port's hit count.
     */
    __u32 source_key = source_port;
    __u64 initial_hits = 1;

    long update_result = bpf_map_update_elem(
        &source_port_hits,
        &source_key,
        &initial_hits,
        BPF_NOEXIST
    );

    if (update_result < 0) {
        __u64 *hits = bpf_map_lookup_elem(
            &source_port_hits,
            &source_key
        );

        if (hits)
            __sync_fetch_and_add(hits, 1);
    }

    __sync_fetch_and_add(&stats->matched, 1);
    __sync_fetch_and_add(&stats->dropped, 1);

    return 2; /* TC_ACT_SHOT */
}

char LICENSE[] SEC("license") = "GPL";
