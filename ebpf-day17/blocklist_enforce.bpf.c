#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/pkt_cls.h>

#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#include "blocklist_map.h"
#include "blocklist_drop_event.h"
#include <linux/tcp.h>
#include <linux/udp.h>

struct vlan_hdr_local {
    __be16 tci;
    __be16 encapsulated_proto;
};

/* Reuse the existing Day 17 pinned map through the userspace loader. */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, API_SENTINEL_BLOCKLIST_MAX_ENTRIES);
    __type(key, __u32);
    __type(value, struct api_sentinel_blocklist_value);
} blocklist SEC(".maps");

/* A separate event stream keeps the existing blocklist map ABI unchanged. */
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 20);
} drop_events SEC(".maps");

static __always_inline int is_vlan_proto(__be16 protocol)
{
    return protocol == bpf_htons(ETH_P_8021Q) ||
           protocol == bpf_htons(ETH_P_8021AD);
}

SEC("classifier")
int enforce_blocklist(struct __sk_buff *skb)
{
    char *data = (char *)(long)skb->data;
    char *data_end = (char *)(long)skb->data_end;
    struct ethhdr *eth = (struct ethhdr *)data;

    if ((char *)(eth + 1) > data_end)
        return TC_ACT_OK;

    __be16 protocol = eth->h_proto;
    __u32 l3_offset = sizeof(*eth);

    /* Parse at most two VLAN tags. */
#pragma unroll
    for (int i = 0; i < 2; i++) {
        if (!is_vlan_proto(protocol))
            break;

        struct vlan_hdr_local *vlan =
            (struct vlan_hdr_local *)(data + l3_offset);

        if ((char *)(vlan + 1) > data_end)
            return TC_ACT_OK;

        protocol = vlan->encapsulated_proto;
        l3_offset += sizeof(*vlan);
    }

    if (protocol != bpf_htons(ETH_P_IP))
        return TC_ACT_OK;

    struct iphdr *ip = (struct iphdr *)(data + l3_offset);
    if ((char *)(ip + 1) > data_end)
        return TC_ACT_OK;

    if (ip->version != 4 || ip->ihl < 5)
        return TC_ACT_OK;

    __u32 ip_header_length = (__u32)ip->ihl * 4;
    if ((char *)ip + ip_header_length > data_end)
        return TC_ACT_OK;

    /* ip->saddr retains the same network-order bytes as the map key. */
    __u32 source_ip = ip->saddr;
    struct api_sentinel_blocklist_value *value =
        bpf_map_lookup_elem(&blocklist, &source_ip);

    if (!value)
        return TC_ACT_OK;

    /* Zero means permanent; expired entries are treated as unblocked. */
    __u64 expires_at = value->expires_at_mono_ns;
    if (expires_at != 0 && expires_at <= bpf_ktime_get_ns())
        return TC_ACT_OK;

    /*
     * Emit an event at the actual drop decision. A full ring buffer must
     * never turn a blocked packet into an allowed packet.
     */
    struct api_sentinel_drop_event *event = bpf_ringbuf_reserve(
        &drop_events, sizeof(*event), 0
    );
    if (event) {
        __builtin_memset(event, 0, sizeof(*event));
        event->captured_at_ns = bpf_ktime_get_ns();
        event->interface_index = skb->ifindex;
        event->source_ip = ip->saddr;
        event->destination_ip = ip->daddr;
        event->protocol = ip->protocol;
        event->rule_id = API_SENTINEL_DROP_RULE_ID;

        /* Non-initial IPv4 fragments do not contain transport ports. */
        if ((bpf_ntohs(ip->frag_off) & 0x1fff) == 0) {
            void *transport = (void *)ip + ip_header_length;
            if (ip->protocol == 6) {
                struct tcphdr *tcp = transport;
                if ((char *)(tcp + 1) <= data_end) {
                    event->source_port = bpf_ntohs(tcp->source);
                    event->destination_port = bpf_ntohs(tcp->dest);
                }
            } else if (ip->protocol == 17) {
                struct udphdr *udp = transport;
                if ((char *)(udp + 1) <= data_end) {
                    event->source_port = bpf_ntohs(udp->source);
                    event->destination_port = bpf_ntohs(udp->dest);
                }
            }
        }

        bpf_ringbuf_submit(event, 0);
    }

    return TC_ACT_SHOT;
}

char LICENSE[] SEC("license") = "GPL";
