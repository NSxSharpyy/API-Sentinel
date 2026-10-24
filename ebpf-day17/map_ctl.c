#define _GNU_SOURCE

#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <linux/bpf.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "blocklist_map.h"

#define NSEC_PER_SEC UINT64_C(1000000000)
#define MAX_TTL_SECONDS (30ULL * 24ULL * 60ULL * 60ULL)

static void report_error(const char *operation, int error)
{
    int code = error < 0 ? -error : error;
    fprintf(stderr, "%s: %s (%d)\n",
            operation, strerror(code), code);
}

static int validate_map(int fd)
{
    struct bpf_map_info info = {};
    __u32 info_len = sizeof(info);

    int err = bpf_obj_get_info_by_fd(fd, &info, &info_len);
    if (err < 0) {
        report_error("Read map metadata", err);
        return -1;
    }

    if (info.type != BPF_MAP_TYPE_HASH ||
        info.key_size != sizeof(__u32) ||
        info.value_size != sizeof(struct api_sentinel_blocklist_value) ||
        info.max_entries != API_SENTINEL_BLOCKLIST_MAX_ENTRIES) {
        fprintf(stderr,
                "Refusing incompatible map: type=%u key=%u value=%u entries=%u\n",
                info.type, info.key_size, info.value_size, info.max_entries);
        return -1;
    }

    return 0;
}

/*
 * create_if_missing is enabled only by the explicit "init" command.
 * Existing pins are never overwritten.
 */
static int open_map(bool create_if_missing)
{
    int fd = bpf_obj_get(API_SENTINEL_BLOCKLIST_PIN);

    if (fd >= 0) {
        if (validate_map(fd) < 0) {
            close(fd);
            return -1;
        }
        return fd;
    }

    if (fd != -ENOENT) {
        report_error("Open pinned blocklist map", fd);
        return -1;
    }

    if (!create_if_missing) {
        fprintf(stderr, "Blocklist map is not initialized; run 'init' first.\n");
        return -1;
    }

    fd = bpf_map_create(
        BPF_MAP_TYPE_HASH,
        API_SENTINEL_BLOCKLIST_MAP_NAME,
        sizeof(__u32),
        sizeof(struct api_sentinel_blocklist_value),
        API_SENTINEL_BLOCKLIST_MAX_ENTRIES,
        NULL
    );

    if (fd < 0) {
        report_error("Create blocklist hash map", fd);
        return -1;
    }

    int err = bpf_obj_pin(fd, API_SENTINEL_BLOCKLIST_PIN);
    if (err < 0) {
        report_error("Pin blocklist map", err);
        close(fd);
        return -1;
    }

    if (validate_map(fd) < 0) {
        close(fd);
        return -1;
    }

    return fd;
}

static int parse_ipv4(const char *text, __u32 *key)
{
    struct in_addr addr;

    if (inet_pton(AF_INET, text, &addr) != 1) {
        fprintf(stderr, "Invalid IPv4 address: %s\n", text);
        return -1;
    }

    uint32_t host = ntohl(addr.s_addr);

    if (host == 0 ||
        host == UINT32_MAX ||
        (host >> 24) == 127 ||
        (host >> 28) == 0xE) {
        fprintf(stderr, "Address is not eligible for blocking: %s\n", text);
        return -1;
    }

    /* Preserve network-order bytes so the key matches ip->saddr in eBPF. */
    *key = addr.s_addr;
    return 0;
}

static int monotonic_now_ns(uint64_t *result)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        perror("clock_gettime");
        return -1;
    }

    *result = (uint64_t)ts.tv_sec * NSEC_PER_SEC + (uint64_t)ts.tv_nsec;
    return 0;
}

static int command_init(void)
{
    int fd = open_map(true);
    if (fd < 0)
        return 1;

    printf("Blocklist map ready.\n");
    printf("Pin: %s\n", API_SENTINEL_BLOCKLIST_PIN);
    printf("Type: HASH; key: 4 bytes; value: 8 bytes; capacity: %u\n",
           API_SENTINEL_BLOCKLIST_MAX_ENTRIES);
    printf("Note: map storage does not itself enforce packet drops.\n");

    close(fd);
    return 0;
}

static int command_block(const char *ip, const char *ttl_text)
{
    char *end = NULL;
    errno = 0;
    unsigned long long ttl = strtoull(ttl_text, &end, 10);

    if (errno || end == ttl_text || *end != '\0' ||
        ttl > MAX_TTL_SECONDS) {
        fprintf(stderr, "TTL must be between 0 and %llu seconds.\n",
                MAX_TTL_SECONDS);
        return 2;
    }

    __u32 key;
    if (parse_ipv4(ip, &key) < 0)
        return 2;

    struct api_sentinel_blocklist_value value = {
        .expires_at_mono_ns = 0
    };

    if (ttl != 0) {
        uint64_t now;
        if (monotonic_now_ns(&now) < 0)
            return 1;

        value.expires_at_mono_ns = now + (uint64_t)ttl * NSEC_PER_SEC;
    }

    int fd = open_map(false);
    if (fd < 0)
        return 1;

    int err = bpf_map_update_elem(fd, &key, &value, BPF_ANY);
    close(fd);

    if (err < 0) {
        report_error("Update blocklist map", err);
        return 1;
    }

    printf("Stored %s (%s).\n", ip,
           ttl == 0 ? "permanent" : "temporary");
    return 0;
}

static int command_unblock(const char *ip)
{
    __u32 key;
    if (parse_ipv4(ip, &key) < 0)
        return 2;

    int fd = open_map(false);
    if (fd < 0)
        return 1;

    int err = bpf_map_delete_elem(fd, &key);
    close(fd);

    if (err == -ENOENT) {
        printf("%s was not present; no change needed.\n", ip);
        return 0;
    }

    if (err < 0) {
        report_error("Delete blocklist entry", err);
        return 1;
    }

    printf("Removed %s from the blocklist map.\n", ip);
    return 0;
}

static int command_show(const char *ip)
{
    __u32 key;
    if (parse_ipv4(ip, &key) < 0)
        return 2;

    int fd = open_map(false);
    if (fd < 0)
        return 1;

    struct api_sentinel_blocklist_value value = {};
    int err = bpf_map_lookup_elem(fd, &key, &value);
    close(fd);

    if (err == -ENOENT) {
        printf("%s is not present.\n", ip);
        return 0;
    }

    if (err < 0) {
        report_error("Read blocklist entry", err);
        return 1;
    }

    if (value.expires_at_mono_ns == 0) {
        printf("%s: permanent entry.\n", ip);
        return 0;
    }

    uint64_t now;
    if (monotonic_now_ns(&now) < 0)
        return 1;

    if (value.expires_at_mono_ns <= now) {
        printf("%s: entry is expired but has not been deleted.\n", ip);
    } else {
        double seconds =
            (double)(value.expires_at_mono_ns - now) / (double)NSEC_PER_SEC;
        printf("%s: expires in approximately %.3f seconds.\n", ip, seconds);
    }

    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr,
        "Usage:\n"
        "  %s init\n"
        "  %s block <IPv4> <TTL-seconds|0>\n"
        "  %s unblock <IPv4>\n"
        "  %s show <IPv4>\n"
        "\n"
        "These commands update map state only; they do not attach a drop program.\n",
        program, program, program, program);
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "init") == 0)
        return command_init();

    if (argc == 4 && strcmp(argv[1], "block") == 0)
        return command_block(argv[2], argv[3]);

    if (argc == 3 && strcmp(argv[1], "unblock") == 0)
        return command_unblock(argv[2]);

    if (argc == 3 && strcmp(argv[1], "show") == 0)
        return command_show(argv[2]);

    usage(argv[0]);
    return 2;
}
