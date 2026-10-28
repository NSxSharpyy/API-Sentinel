#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

#define SOURCE_PORT 50355
#define DEST_PORT   5004

struct day19_stats {
    __u64 seen;
    __u64 matched;
    __u64 dropped;
};

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct day19_stats);
} day19_stats_map SEC(".maps");

static __always_inline int is_target_request(struct __sk_buff *skb)
{
    unsigned char ip[20];
    unsigned char tcp[20];
    unsigned char payload[29];

    const __u32 ip_offset = 14;

    if (bpf_skb_load_bytes(skb, ip_offset, ip, sizeof(ip)) < 0)
        return 0;
    if ((ip[0] >> 4) != 4 || ip[9] != 6 || (ip[0] & 15) < 5)
        return 0;

    __u32 ip_header_len = (ip[0] & 15) * 4;
    __u32 tcp_offset = ip_offset + ip_header_len;

    if (bpf_skb_load_bytes(skb, tcp_offset, tcp, sizeof(tcp)) < 0)
        return 0;

    __u16 src = ((__u16)tcp[0] << 8) | tcp[1];
    __u16 dst = ((__u16)tcp[2] << 8) | tcp[3];

    if (src != SOURCE_PORT || dst != DEST_PORT)
        return 0;

    __u32 tcp_header_len = (tcp[12] >> 4) * 4;
    if (tcp_header_len < 20)
        return 0;

    __u32 payload_offset = tcp_offset + tcp_header_len;
    if (bpf_skb_load_bytes(
            skb, payload_offset, payload, sizeof(payload)) < 0)
        return 0;

    const char prefix[] = "GET /api/v2/billing/invoices/";
#pragma unroll
    for (int i = 0; i < sizeof(prefix) - 1; i++) {
        if (payload[i] != prefix[i])
            return 0;
    }

    return 1;
}

SEC("classifier")
int day19_request_drop(struct __sk_buff *skb)
{
    __u32 key = 0;
    struct day19_stats *stats =
        bpf_map_lookup_elem(&day19_stats_map, &key);

    if (!stats)
        return 0;

    __sync_fetch_and_add(&stats->seen, 1);

    if (is_target_request(skb)) {
        __sync_fetch_and_add(&stats->matched, 1);
        __sync_fetch_and_add(&stats->dropped, 1);
        return 2; /* TC_ACT_SHOT */
    }

    return 0; /* TC_ACT_UNSPEC: pass traffic onward */
}

char LICENSE[] SEC("license") = "GPL";
