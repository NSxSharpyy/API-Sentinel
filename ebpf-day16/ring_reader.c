
#include <unistd.h>
#include <errno.h>
#include <arpa/inet.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include "api_sentinel_event.h"

#define MAX_PAYLOAD API_SENTINEL_MAX_PAYLOAD



static volatile sig_atomic_t running = 1;
static uint64_t packet_counter = 0;

static void handle_signal(int signal_number)
{
    (void)signal_number;
    running = 0;
}

static int handle_event(
    void *context,
    void *data,
    size_t data_size
)
{
    (void)context;

    if (data_size < sizeof(struct api_sentinel_event)) {
        fprintf(stderr, "Unexpected event size: %zu\n", data_size);
        return 0;
    }

    const struct api_sentinel_event *event = data;
    char src_ip[INET_ADDRSTRLEN];
    char dst_ip[INET_ADDRSTRLEN];

    struct in_addr src_addr = { .s_addr = event->source_ip };
    struct in_addr dst_addr = { .s_addr = event->destination_ip };

    if (!inet_ntop(AF_INET, &src_addr, src_ip, sizeof(src_ip)) ||
        !inet_ntop(AF_INET, &dst_addr, dst_ip, sizeof(dst_ip))) {
        fprintf(stderr, "Could not format IP address\n");
        return 0;
    }

    printf(
        "{\"packet_id\":\"ebpf-%llu\","
        "\"captured_at_ns\":%llu,"
        "\"packet_length\":%u,"
        "\"interface_index\":%u,"
        "\"source_ip\":\"%s\","
        "\"destination_ip\":\"%s\","
        "\"source_port\":%u,"
        "\"destination_port\":%u,"
        "\"protocol\":%u,"
        "\"sequence_number\":%u,"
        "\"tcp_flags\":%u,"
        "\"payload_hex\":\"",
        (unsigned long long)++packet_counter,
        (unsigned long long)event->captured_at_ns,
        event->packet_length,
        event->interface_index,
        src_ip,
        dst_ip,
        (unsigned int)event->source_port,
        (unsigned int)event->destination_port,
        (unsigned int)event->protocol,
        event->sequence_number,
        (unsigned int)event->tcp_flags
    );

    uint16_t payload_length = event->payload_length;
    if (payload_length > MAX_PAYLOAD)
        payload_length = MAX_PAYLOAD;

    for (uint16_t i = 0; i < payload_length; i++)
        printf("%02x", event->payload[i]);

    puts("\"}");
    fflush(stdout);

    return 0;
}

int main(int argc, char **argv)
{
    const char *map_path = argc > 1
        ? argv[1]
        : "/sys/fs/bpf/api_sentinel_day16_events";

    struct ring_buffer *rb;
    int map_fd;
    int result = 0;

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    map_fd = bpf_obj_get(map_path);
    if (map_fd < 0) {
        fprintf(stderr, "Cannot open pinned map: %s\n", map_path);
        return 1;
    }

    rb = ring_buffer__new(map_fd, handle_event, NULL, NULL);
    if (!rb) {
        fprintf(stderr, "Failed to create ring buffer reader\n");
        close(map_fd);
        return 1;
    }

    fprintf(stderr, "JSON reader listening on %s\n", map_path);

    while (running) {
        result = ring_buffer__poll(rb, 250);

        if (result == -EINTR) {
            result = 0;
            break;
        }

        if (result < 0) {
            fprintf(stderr, "Ring buffer poll failed: %d\n", result);
            break;
        }
    }

    ring_buffer__free(rb);
    close(map_fd);

    fprintf(stderr, "Reader stopped.\n");
    return result < 0 ? 1 : 0;
}

char LICENSE[] = "GPL";
