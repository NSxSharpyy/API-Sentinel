#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "blocklist_drop_event.h"

static volatile sig_atomic_t running = 1;

static void handle_signal(int signal_number)
{
    (void)signal_number;
    running = 0;
}

static int handle_event(void *context, void *data, size_t size)
{
    (void)context;

    if (size != sizeof(struct api_sentinel_drop_event)) {
        fprintf(stderr, "Unexpected Day 19 event size: %zu\n", size);
        return 0;
    }

    const struct api_sentinel_drop_event *event = data;
    struct in_addr src = { .s_addr = event->source_ip };
    struct in_addr dst = { .s_addr = event->destination_ip };
    char source_ip[INET_ADDRSTRLEN];
    char destination_ip[INET_ADDRSTRLEN];

    if (!inet_ntop(AF_INET, &src, source_ip, sizeof(source_ip)) ||
        !inet_ntop(AF_INET, &dst, destination_ip, sizeof(destination_ip))) {
        fprintf(stderr, "Could not format Day 19 event IP address\n");
        return 0;
    }

    const char *protocol = "OTHER";
    if (event->protocol == IPPROTO_TCP)
        protocol = "TCP";
    else if (event->protocol == IPPROTO_UDP)
        protocol = "UDP";

    const char *rule_id = event->rule_id == API_SENTINEL_DROP_RULE_ID
        ? API_SENTINEL_DROP_RULE_NAME : "unknown_enforcement_rule";

    printf(
        "{\"captured_at_ns\":%llu,\"interface_index\":%u,"
        "\"source_ip\":\"%s\",\"destination_ip\":\"%s\","
        "\"source_port\":%u,\"destination_port\":%u,"
        "\"protocol\":\"%s\",\"rule_id\":\"%s\"}\n",
        (unsigned long long)event->captured_at_ns,
        event->interface_index,
        source_ip,
        destination_ip,
        (unsigned int)event->source_port,
        (unsigned int)event->destination_port,
        protocol,
        rule_id
    );
    fflush(stdout);
    return 0;
}

int main(int argc, char **argv)
{
    const char *pin_path = argc > 1
        ? argv[1] : API_SENTINEL_DROP_EVENTS_PIN;

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    int map_fd = bpf_obj_get(pin_path);
    if (map_fd < 0) {
        fprintf(stderr, "Cannot open drop-event map %s: %s\n",
                pin_path, strerror(errno));
        return 1;
    }

    struct ring_buffer *ring = ring_buffer__new(
        map_fd, handle_event, NULL, NULL
    );
    if (!ring) {
        fprintf(stderr, "Cannot create Day 19 ring-buffer reader\n");
        close(map_fd);
        return 1;
    }

    fprintf(stderr, "Day 19 audit reader listening on %s\n", pin_path);

    int result = 0;
    while (running) {
        int rc = ring_buffer__poll(ring, 250);
        if (rc == -EINTR) {
            result = 0;
            break;
        }
        if (rc < 0) {
            fprintf(stderr, "Day 19 ring-buffer poll failed: %d\n", rc);
            result = 1;
            break;
        }
    }

    ring_buffer__free(ring);
    close(map_fd);
    fprintf(stderr, "Day 19 audit reader stopped\n");
    return result;
}
