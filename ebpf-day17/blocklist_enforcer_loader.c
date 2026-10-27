#define _GNU_SOURCE

#include <errno.h>
#include <linux/bpf.h>
#include <net/if.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>

#include "blocklist_map.h"
#include "blocklist_drop_event.h"
#include <errno.h>

#define FILTER_HANDLE 0xA517U
#define FILTER_PRIORITY 49151U
#define ENABLE_ENV "API_SENTINEL_ENABLE_PACKET_DROP"

static volatile sig_atomic_t stopping;

static void on_signal(int signo)
{
    (void)signo;
    stopping = 1;
}

static void report_error(const char *what, int err)
{
    int code = err < 0 ? -err : err;
    fprintf(stderr, "%s: %s (%d)\n", what, strerror(code), code);
}

static bool is_lab_interface(const char *name)
{
    return strncmp(name, "api-sntl-", 9) == 0;
}

static void init_hook(struct bpf_tc_hook *hook, int ifindex)
{
    memset(hook, 0, sizeof(*hook));
    hook->sz = sizeof(*hook);
    hook->ifindex = ifindex;
    hook->attach_point = BPF_TC_INGRESS;
}

static void init_filter_opts(struct bpf_tc_opts *opts)
{
    memset(opts, 0, sizeof(*opts));
    opts->sz = sizeof(*opts);
    opts->handle = FILTER_HANDLE;
    opts->priority = FILTER_PRIORITY;
}

static int detach_filter(const char *name)
{
    if (geteuid() != 0 || !is_lab_interface(name)) {
        fprintf(stderr,
                "Detach requires sudo and an api-sntl-* interface.\n");
        return 2;
    }

    unsigned int index = if_nametoindex(name);
    if (!index) {
        /* A removed virtual interface cannot retain its TC filter. */
        printf("Interface %s no longer exists; no TC filter can remain on it.\n",
               name);
        return 0;
    }

    struct bpf_tc_hook hook;
    struct bpf_tc_opts opts;
    init_hook(&hook, (int)index);
    init_filter_opts(&opts);

    int err = bpf_tc_detach(&hook, &opts);
    if (err == -ENOENT) {
        printf("No enforcement filter found on %s.\n", name);
        return 0;
    }
    if (err < 0) {
        report_error("Detach enforcement filter", err);
        return 1;
    }

    printf("Detached enforcement filter from %s.\n", name);
    return 0;
}

static int validate_map(int fd)
{
    struct bpf_map_info info = {};
    __u32 info_len = sizeof(info);

    int err = bpf_obj_get_info_by_fd(fd, &info, &info_len);
    if (err < 0) {
        report_error("Read pinned map metadata", err);
        return -1;
    }

    if (info.type != BPF_MAP_TYPE_HASH ||
        info.key_size != sizeof(__u32) ||
        info.value_size != sizeof(struct api_sentinel_blocklist_value) ||
        info.max_entries != API_SENTINEL_BLOCKLIST_MAX_ENTRIES ||
        strncmp((const char *)info.name, API_SENTINEL_BLOCKLIST_MAP_NAME,
                sizeof(info.name)) != 0) {
        fprintf(stderr, "Pinned blocklist map ABI/name mismatch; refusing.\n");
        return -1;
    }

    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr,
        "Attach: sudo %s <object.o> <api-sntl-test-interface> "
        "--enable-packet-drop\n"
        "Detach: sudo %s --detach <api-sntl-test-interface> "
        "--confirm-detach\n"
        "Attach also requires %s=1.\n",
        program, program, ENABLE_ENV);
}

int main(int argc, char **argv)
{
    if (argc == 4 && strcmp(argv[1], "--detach") == 0 &&
        strcmp(argv[3], "--confirm-detach") == 0)
        return detach_filter(argv[2]);

    if (argc != 4 || strcmp(argv[3], "--enable-packet-drop") != 0) {
        usage(argv[0]);
        return 2;
    }

    const char *interface_name = argv[2];
    const char *enabled = getenv(ENABLE_ENV);

    if (!is_lab_interface(interface_name) ||
        !enabled || strcmp(enabled, "1") != 0) {
        fprintf(stderr,
            "Refusing attach: use api-sntl-* and set %s=1.\n",
            ENABLE_ENV);
        return 2;
    }
    if (geteuid() != 0) {
        fprintf(stderr, "Attach requires sudo.\n");
        return 1;
    }

    unsigned int index = if_nametoindex(interface_name);
    if (!index) {
        fprintf(stderr, "Interface does not exist: %s\n", interface_name);
        return 1;
    }

    int map_fd = bpf_obj_get(API_SENTINEL_BLOCKLIST_PIN);
    if (map_fd < 0) {
        report_error("Open existing blocklist map; initialize it first",
                     map_fd);
        return 1;
    }
    if (validate_map(map_fd) < 0) {
        close(map_fd);
        return 1;
    }

    libbpf_set_strict_mode(LIBBPF_STRICT_ALL);

    struct bpf_object *obj = bpf_object__open_file(argv[1], NULL);
    long open_error = libbpf_get_error(obj);
    if (open_error) {
        close(map_fd);
        report_error("Open BPF object", (int)open_error);
        return 1;
    }

    int result = 1;
    bool attached = false;
    bool drop_events_was_pinned = false;
    struct bpf_tc_hook hook;
    struct bpf_tc_opts opts;
    struct bpf_map *map = bpf_object__find_map_by_name(obj, "blocklist");
    struct bpf_map *drop_events_map =
        bpf_object__find_map_by_name(obj, "drop_events");
    struct bpf_program *prog =
        bpf_object__find_program_by_name(obj, "enforce_blocklist");

    if (!map || !prog || !drop_events_map) {
        fprintf(stderr, "Object is missing the expected map/program.\n");
        goto cleanup;
    }

    int err = bpf_map__reuse_fd(map, map_fd);
    close(map_fd);
    map_fd = -1;
    if (err < 0) {
        report_error("Reuse pinned map", err);
        goto cleanup;
    }

    int drop_events_fd = bpf_obj_get(API_SENTINEL_DROP_EVENTS_PIN);
    if (drop_events_fd >= 0) {
        err = bpf_map__reuse_fd(drop_events_map, drop_events_fd);
        close(drop_events_fd);
        if (err < 0) {
            report_error("Reuse pinned drop-event ring buffer", err);
            goto cleanup;
        }
        drop_events_was_pinned = true;
    } else if (drop_events_fd != -ENOENT && errno != ENOENT) {
        int code = drop_events_fd < -1 ? drop_events_fd : -errno;
        report_error("Open pinned drop-event ring buffer", code);
        goto cleanup;
    }

    err = bpf_object__load(obj);
    if (err < 0) {
        report_error("Load enforcement program", err);
        goto cleanup;
    }

    if (!drop_events_was_pinned) {
        err = bpf_map__pin(drop_events_map, API_SENTINEL_DROP_EVENTS_PIN);
        if (err < 0) {
            report_error("Pin Day 19 drop-event ring buffer", err);
            goto cleanup;
        }
    }

    init_hook(&hook, (int)index);
    err = bpf_tc_hook_create(&hook);
    if (err < 0 && err != -EEXIST) {
        report_error("Create TC ingress hook", err);
        goto cleanup;
    }

    init_filter_opts(&opts);
    opts.prog_fd = bpf_program__fd(prog);

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    err = bpf_tc_attach(&hook, &opts);
    if (err < 0) {
        report_error("Attach enforcement filter", err);
        goto cleanup;
    }
    attached = true;
    result = 0;

    printf("Experimental enforcement attached to %s.\n", interface_name);
    printf("Handle=0x%x; priority=%u. Ctrl+C requests detach.\n",
           FILTER_HANDLE, FILTER_PRIORITY);
    fflush(stdout);

    while (!stopping)
        sleep(1);

cleanup:
    if (attached) {
        /* Detach by our unique handle/priority, without replacing other filters. */
        struct bpf_tc_opts detach_opts;
        init_filter_opts(&detach_opts);
        err = bpf_tc_detach(&hook, &detach_opts);
        if (err == -ENODEV && if_nametoindex(interface_name) == 0) {
            /* The test interface disappeared while the process was running. */
            printf("Interface %s was removed; its TC filter no longer exists.\n",
                   interface_name);
        } else if (err < 0 && err != -ENOENT) {
            report_error("Detach on shutdown", err);
            fprintf(stderr,
                "Manual recovery: sudo %s --detach %s --confirm-detach\n",
                argv[0], interface_name);
            result = 1;
        } else {
            printf("Enforcement filter detached.\n");
        }
    }

    if (map_fd >= 0)
        close(map_fd);
    bpf_object__close(obj);
    return result;
}
