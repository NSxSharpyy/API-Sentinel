#define _GNU_SOURCE
#include <bpf/libbpf.h>
#include <errno.h>
#include <net/if.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define API_SENTINEL_PIN_PATH "/sys/fs/bpf/api_sentinel_day16_events"
#define API_SENTINEL_TC_HANDLE 0xA516
#define API_SENTINEL_TC_PRIORITY 49152

static volatile sig_atomic_t stop_requested;

static void on_signal(int signo)
{
    (void)signo;
    stop_requested = 1;
}

static void report_libbpf_error(const char *what, int error)
{
    fprintf(stderr, "%s: %s (%d)\n", what,
            strerror(error < 0 ? -error : error), error);
}

int main(int argc, char **argv)
{
    const char *object_path = argc > 1 ? argv[1] : "packet_capture.bpf.o";
    const char *interface_name = argc > 2 ? argv[2] : "lo";
    unsigned int ifindex = if_nametoindex(interface_name);
    struct bpf_object *object = NULL;
    struct bpf_program *program;
    struct bpf_map *map;
    struct bpf_tc_hook hook = {};
    struct bpf_tc_opts opts = {};
    int err;
    int map_pinned = 0;
    int tc_attached = 0;

    if (geteuid() != 0) {
        fprintf(stderr, "Run this loader with sudo; BPF attach requires privileges.\n");
        return 1;
    }
    if (!ifindex) {
        fprintf(stderr, "Interface not found: %s\n", interface_name);
        return 1;
    }
    if (access(API_SENTINEL_PIN_PATH, F_OK) == 0) {
        fprintf(stderr,
                "Refusing to overwrite existing pinned map: %s\n"
                "Stop the reader and inspect this pin before removing it.\n",
                API_SENTINEL_PIN_PATH);
        return 1;
    }

    libbpf_set_strict_mode(LIBBPF_STRICT_ALL);
    object = bpf_object__open_file(object_path, NULL);
    err = (int)libbpf_get_error(object);
    if (err) {
        object = NULL;
        report_libbpf_error("Open BPF object", err);
        return 1;
    }

    err = bpf_object__load(object);
    if (err) {
        report_libbpf_error("Load BPF object", err);
        goto cleanup;
    }

    program = bpf_object__find_program_by_name(object, "capture_packets");
    map = bpf_object__find_map_by_name(object, "events");
    if (!program || !map) {
        fprintf(stderr, "BPF object must contain program 'capture_packets' and map 'events'.\n");
        err = -ENOENT;
        goto cleanup;
    }

    err = bpf_map__pin(map, API_SENTINEL_PIN_PATH);
    if (err) {
        report_libbpf_error("Pin ring-buffer map (is bpffs mounted?)", err);
        goto cleanup;
    }
    map_pinned = 1;

    hook.sz = sizeof(hook);
    hook.ifindex = (int)ifindex;
    hook.attach_point = BPF_TC_INGRESS;
    err = bpf_tc_hook_create(&hook);
    if (err && err != -EEXIST) {
        report_libbpf_error("Create TC ingress hook", err);
        goto cleanup;
    }
    /* An existing clsact qdisc is fine; the error only means it already exists. */
    err = 0;

    opts.sz = sizeof(opts);
    opts.prog_fd = bpf_program__fd(program);
    opts.handle = API_SENTINEL_TC_HANDLE;
    opts.priority = API_SENTINEL_TC_PRIORITY;
    err = bpf_tc_attach(&hook, &opts);
    if (err) {
        report_libbpf_error("Attach TC ingress program", err);
        goto cleanup;
    }
    tc_attached = 1;

    printf("API-Sentinel Day 16 producer active on interface %s (ifindex %u).\n",
           interface_name, ifindex);
    printf("Pinned ring-buffer map: %s\n", API_SENTINEL_PIN_PATH);
    printf("Capturing IPv4 TCP packets with non-empty payloads; Ctrl+C to stop.\n");
    fflush(stdout);

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    while (!stop_requested)
        sleep(1);

    printf("Stopping producer...\n");

cleanup:
    if (tc_attached) {
        /*
         * Detach options must not reuse prog_fd or other attachment
         * fields. libbpf expects only the handle and priority here.
         */
        struct bpf_tc_opts detach_opts = {};
        detach_opts.sz = sizeof(detach_opts);
        detach_opts.handle = API_SENTINEL_TC_HANDLE;
        detach_opts.priority = API_SENTINEL_TC_PRIORITY;

        int detach_err = bpf_tc_detach(&hook, &detach_opts);
        if (detach_err && detach_err != -ENOENT) {
            report_libbpf_error("Detach TC ingress program", detach_err);
            if (!err)
                err = detach_err;
        } else {
            tc_attached = 0;
        }
    }

    if (map_pinned && !tc_attached) {
        int unpin_err = bpf_map__unpin(map, API_SENTINEL_PIN_PATH);
        if (unpin_err && unpin_err != -ENOENT) {
            report_libbpf_error("Unpin ring-buffer map", unpin_err);
            if (!err)
                err = unpin_err;
        }
    } else if (map_pinned && tc_attached) {
        fprintf(stderr,
                "Keeping ring-buffer pin because TC detach failed: %s\n",
                API_SENTINEL_PIN_PATH);
    }

    bpf_object__close(object);
    return err ? 1 : 0;
}
