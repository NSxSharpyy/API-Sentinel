#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/pkt_cls.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#include "api_sentinel_event.h"

/* Explicit IPv4/TCP constants avoid userspace/kernel header differences. */
#define API_SENTINEL_IPPROTO_TCP 6
#define API_SENTINEL_IP_MF       0x2000
#define API_SENTINEL_IP_OFFSET   0x1fff

struct vlan_hdr_local {
    __be16 tci;
    __be16 encapsulated_proto;
};

struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 24); /* 16 MiB */
} events SEC(".maps");

/*
 * Local-lab TCP payload capture for API-Sentinel Day 16.
 * Attach only to loopback initially, so tests stay local to this WSL VM.
 * Supports IPv4 TCP with Ethernet or loopback/network-layer packet starts.
 * Non-initial IP fragments and IPv6 are intentionally ignored.
 */
SEC("classifier")
int capture_packets(struct __sk_buff *skb)
{
    char *data = (char *)(long)skb->data;
    char *data_end = (char *)(long)skb->data_end;
    __u32 l3_offset = 0;
    __be16 ether_proto = 0;

    if (data + 1 > data_end)
        return TC_ACT_OK;

    /* On loopback, skb data commonly starts at the IPv4 header. */
    if (((unsigned char)data[0] >> 4) == 4) {
        l3_offset = 0;
    } else {
        struct ethhdr *eth = (struct ethhdr *)data;
        if ((char *)(eth + 1) > data_end)
            return TC_ACT_OK;

        ether_proto = eth->h_proto;
        l3_offset = sizeof(*eth);

        if (ether_proto == bpf_htons(ETH_P_8021Q) ||
            ether_proto == bpf_htons(ETH_P_8021AD)) {
            struct vlan_hdr_local *vlan =
                (struct vlan_hdr_local *)(data + l3_offset);
            if ((char *)(vlan + 1) > data_end)
                return TC_ACT_OK;
            ether_proto = vlan->encapsulated_proto;
            l3_offset += sizeof(*vlan);
        }

        if (ether_proto != bpf_htons(ETH_P_IP))
            return TC_ACT_OK;
    }

    struct iphdr *ip = (struct iphdr *)(data + l3_offset);
    if ((char *)(ip + 1) > data_end)
        return TC_ACT_OK;
    if (ip->version != 4 || ip->ihl < 5 || ip->protocol != API_SENTINEL_IPPROTO_TCP)
        return TC_ACT_OK;

    __u32 ip_header_length = (__u32)ip->ihl * 4;
    if (ip_header_length < sizeof(*ip) ||
        (char *)ip + ip_header_length > data_end)
        return TC_ACT_OK;

    /* Don't parse non-initial or fragmented IPv4 TCP packets. */
    __u16 fragment_bits = bpf_ntohs(ip->frag_off);
    if (fragment_bits & (API_SENTINEL_IP_MF | API_SENTINEL_IP_OFFSET))
        return TC_ACT_OK;

    struct tcphdr *tcp = (struct tcphdr *)((char *)ip + ip_header_length);
    if ((char *)(tcp + 1) > data_end)
        return TC_ACT_OK;

    __u32 tcp_header_length = (__u32)tcp->doff * 4;
    if (tcp_header_length < sizeof(*tcp) ||
        (char *)tcp + tcp_header_length > data_end)
        return TC_ACT_OK;

    __u32 ip_total_length = bpf_ntohs(ip->tot_len);
    if (ip_total_length < ip_header_length + tcp_header_length)
        return TC_ACT_OK;

    __u32 payload_offset = l3_offset + ip_header_length + tcp_header_length;
    __u32 payload_length = ip_total_length - ip_header_length - tcp_header_length;
    if (payload_offset > skb->len || payload_length > skb->len - payload_offset)
        return TC_ACT_OK;

    __u32 copy_length = payload_length;
    if (copy_length > API_SENTINEL_MAX_PAYLOAD)
        copy_length = API_SENTINEL_MAX_PAYLOAD;

    /*
     * Reload to prevent compiler simplification of the zero check, then
     * re-establish both bounds for the kernel verifier.
     */
    volatile __u32 copy_length_reload = copy_length;
    __u32 safe_copy_length = copy_length_reload;

    if (safe_copy_length > API_SENTINEL_MAX_PAYLOAD)
        safe_copy_length = API_SENTINEL_MAX_PAYLOAD;

    struct api_sentinel_event *event =
        bpf_ringbuf_reserve(&events, sizeof(*event), 0);
    if (!event)
        return TC_ACT_OK;

    event->captured_at_ns = bpf_ktime_get_ns();
    event->packet_length = skb->len;
    event->interface_index = skb->ifindex;
    event->source_ip = ip->saddr;       /* preserve IPv4 bytes for inet_ntop */
    event->destination_ip = ip->daddr;  /* preserve IPv4 bytes for inet_ntop */
    event->sequence_number = bpf_ntohl(tcp->seq);
    event->source_port = bpf_ntohs(tcp->source);
    event->destination_port = bpf_ntohs(tcp->dest);
    event->payload_length = (__u16)safe_copy_length;
    event->protocol = API_SENTINEL_IPPROTO_TCP;
    event->tcp_flags = ((__u8 *)tcp)[13];

    if (safe_copy_length > 0) {
        if (bpf_skb_load_bytes(skb, payload_offset, event->payload, safe_copy_length) < 0) {
            bpf_ringbuf_discard(event, 0);
            return TC_ACT_OK;
        }
    }

    bpf_ringbuf_submit(event, 0);
    return TC_ACT_OK;
}

char LICENSE[] SEC("license") = "GPL";
