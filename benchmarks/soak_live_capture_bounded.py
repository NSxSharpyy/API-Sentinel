#!/usr/bin/env python3
"""Duration-based soak test for the live API-Sentinel loopback pipeline."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

MIB = 1024 * 1024

COUNTER_KEYS = (
    "accepted_packet_count",
    "accepted_tcp_event_count",
    "rejected_packet_count",
    "dropped_packet_count",
    "tcp_stream_limit_rejection_count",
    "tcp_reassembly_buffer_overflow_count",
    "persistence_persisted_count",
    "persistence_failed_count",
    "persistence_rejected_count",
    "http_parsed_request_count",
    "http_parsed_response_count",
    "http_dropped_request_count",
    "http_expired_request_count",
    "http_capacity_evicted_request_count",
    "http_connection_closed_request_count",
    "transaction_processing_count",
)

QUEUE_KEYS = (
    "raw_packet_queue",
    "header_queue",
    "metadata_queue",
    "persistence_queue_size",
)


def get_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "api-sentinel-soak-test/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        result = json.loads(response.read().decode("utf-8"))

    if not isinstance(result, dict):
        raise RuntimeError(f"Expected a JSON object from {url}")
    return result


def read_rss_kib(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return None


def aggregate_rss_kib(pids: list[int]) -> int | None:
    values = [read_rss_kib(pid) for pid in pids]
    available = [value for value in values if value is not None]
    return sum(available) if available else None


def discover_uvicorn_pids() -> list[int]:
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
        except (FileNotFoundError, PermissionError):
            continue
        if b"uvicorn" in command and b"app.main:app" in command:
            found.append(int(entry.name))
    return sorted(set(found))


def percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    values = sorted(samples)
    index = round((len(values) - 1) * p)
    return values[max(0, min(len(values) - 1, index))]


def hit_root(base_url: str, timeout: float) -> tuple[bool, float, str | None]:
    started = time.perf_counter_ns()
    try:
        payload = get_json(base_url.rstrip("/") + "/", timeout)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        if payload.get("status") != "running":
            return False, elapsed_ms, "root endpoint did not report status=running"
        return True, elapsed_ms, None
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return False, elapsed_ms, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--duration-seconds", type=float, default=300)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--drain-timeout", type=float, default=60)
    parser.add_argument("--max-rss-growth-mib", type=float, default=128)
    parser.add_argument(
        "--pid", type=int, action="append", dest="pids",
        help="Uvicorn PID to sample; repeat to include more processes.",
    )
    args = parser.parse_args()

    if (
        args.duration_seconds <= 0
        or args.concurrency <= 0
        or args.timeout <= 0
        or args.drain_timeout <= 0
        or args.max_rss_growth_mib < 0
    ):
        parser.error("durations and concurrency must be positive; RSS limit must be non-negative")

    pids = sorted(set(args.pids or discover_uvicorn_pids()))
    if not pids:
        parser.error("No Uvicorn PID found; pass --pid <PID>.")

    initial_rss = aggregate_rss_kib(pids)
    if initial_rss is None:
        parser.error(f"Could not read RSS for PID(s): {pids}")

    base_url = args.base_url.rstrip("/")
    try:
        baseline = get_json(base_url + "/queue-status", args.timeout)
    except Exception as exc:
        parser.error(f"queue-status is not reachable: {exc}")

    if baseline.get("capture_running") is not True:
        parser.error("Capture is not running. Start the real capture pipeline first.")

    baseline_counts = {
        key: int(baseline.get(key, 0) or 0) for key in COUNTER_KEYS
    }

    parser_required_keys = {
        "http_pending_request_count",
        "http_unmatched_response_count",
    }
    missing_parser_keys = parser_required_keys - baseline.keys()
    if missing_parser_keys:
        parser.error(
            "Queue status is missing HTTP parser gauges: "
            + ", ".join(sorted(missing_parser_keys))
        )

    baseline_pending = int(baseline["http_pending_request_count"] or 0)
    baseline_unmatched = int(
        baseline["http_unmatched_response_count"] or 0
    )

    stop_load = threading.Event()
    stop_rss = threading.Event()
    data_lock = threading.Lock()
    # Bound test-harness memory during long-duration runs.
    latencies_ms = deque(maxlen=10_000)
    errors: list[str] = []
    stats = {"attempted": 0, "successful": 0, "failed": 0}
    rss_stats = {
        "peak_kib": initial_rss,
        "last_kib": initial_rss,
        "sample_count": 1,
    }

    def sample_rss() -> None:
        # Five-second sampling avoids millions of retained samples.
        while not stop_rss.wait(5.0):
            value = aggregate_rss_kib(pids)
            if value is not None:
                with data_lock:
                    rss_stats["last_kib"] = value
                    rss_stats["peak_kib"] = max(
                        rss_stats["peak_kib"], value
                    )
                    rss_stats["sample_count"] += 1

    def worker() -> None:
        while not stop_load.is_set():
            ok, latency, error = hit_root(base_url, args.timeout)
            with data_lock:
                stats["attempted"] += 1
                latencies_ms.append(latency)
                if ok:
                    stats["successful"] += 1
                else:
                    stats["failed"] += 1
                    if len(errors) < 5:
                        errors.append(
                            error or "root endpoint returned an unexpected result"
                        )

    rss_monitor = threading.Thread(target=sample_rss, daemon=True)
    rss_monitor.start()

    started = time.perf_counter()
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    )
    workers = [
        executor.submit(worker) for _ in range(args.concurrency)
    ]

    try:
        print(
            f"Soak test running for {args.duration_seconds:.0f}s "
            f"at concurrency {args.concurrency}."
        )
        time.sleep(args.duration_seconds)
    except KeyboardInterrupt:
        print("\nInterrupt received; stopping new requests and draining.")
    finally:
        stop_load.set()
        for future in workers:
            future.result()
        executor.shutdown(wait=True)

    load_elapsed = time.perf_counter() - started

    print(f"Load stopped. Allowing up to {args.drain_timeout:.0f}s to drain.")
    time.sleep(args.drain_timeout)

    try:
        final_metrics = get_json(base_url + "/queue-status", args.timeout)
    except Exception as exc:
        stop_rss.set()
        rss_monitor.join(timeout=1)
        print(f"FAIL: unable to retrieve final metrics: {exc}")
        return 2
    finally:
        stop_rss.set()
        rss_monitor.join(timeout=1)

    required_keys = (
        set(COUNTER_KEYS)
        | set(QUEUE_KEYS)
        | parser_required_keys
        | {"capture_running"}
    )
    missing = sorted(required_keys - final_metrics.keys())
    if missing:
        print("FAIL: final metrics are missing: " + ", ".join(missing))
        return 2

    final_counts = {
        key: int(final_metrics.get(key, 0) or 0) for key in COUNTER_KEYS
    }
    deltas = {
        key: final_counts[key] - baseline_counts[key]
        for key in COUNTER_KEYS
    }

    final_pending = int(final_metrics["http_pending_request_count"] or 0)
    final_unmatched = int(
        final_metrics["http_unmatched_response_count"] or 0
    )
    pending_delta = final_pending - baseline_pending
    unmatched_delta = final_unmatched - baseline_unmatched

    request_accounted = (
        deltas["transaction_processing_count"]
        + deltas["http_dropped_request_count"]
        + pending_delta
    )
    request_residual = (
        deltas["http_parsed_request_count"] - request_accounted
    )

    response_accounted = (
        deltas["transaction_processing_count"] + unmatched_delta
    )
    response_residual = (
        deltas["http_parsed_response_count"] - response_accounted
    )

    drop_reason_total = (
        deltas["http_expired_request_count"]
        + deltas["http_capacity_evicted_request_count"]
        + deltas["http_connection_closed_request_count"]
    )

    successful = stats["successful"]
    attempted = stats['attempted']
    rss_growth_mib = (rss_stats['peak_kib'] - initial_rss) / 1024
    response_rate = successful / load_elapsed if load_elapsed > 0 else 0

    print("\nAPI-Sentinel live capture soak-test results")
    print("Boundary: HTTP client -> loopback capture -> parser -> persistence")
    print("Not a physical-NIC or production-database benchmark.")
    print(f"Configured load duration: {args.duration_seconds:.1f}s")
    print(f"Actual load window: {load_elapsed:.1f}s")
    print(f"Completed requests: {attempted}; successful: {successful}")
    print(f"Successful response rate: {response_rate:.1f}/s")
    print(
        f"Latency p50={percentile(latencies_ms, .50):.3f}ms; "
        f"p95={percentile(latencies_ms, .95):.3f}ms; "
        f"p99={percentile(latencies_ms, .99):.3f}ms"
    )

    print("Counter deltas:")
    for key, value in deltas.items():
        print(f"  {key}: {value}")

    print("\nHTTP transaction accounting:")
    print(
        f"  Pending requests: baseline={baseline_pending}, "
        f"final={final_pending}, delta={pending_delta}"
    )
    print(f"  Unmatched responses delta: {unmatched_delta}")
    print(
        f"  Request accounting residual: {request_residual} "
        "(expected 0)"
    )
    print(
        f"  Response accounting residual: {response_residual} "
        "(expected 0; root endpoint uses ordinary final responses)"
    )
    print(
        f"  Drop-reason total: {drop_reason_total}; "
        f"aggregate dropped: {deltas['http_dropped_request_count']}"
    )

    print(
        f"RSS baseline={initial_rss / 1024:.1f}MiB; "
        f"sampled peak={rss_stats['peak_kib'] / 1024:.1f}MiB; "
        f"growth={rss_growth_mib:.1f}MiB"
    )
    print(
        f"RSS samples: {rss_stats['sample_count']} "
        "(5-second interval)"
    )
    print(
        "Latency percentiles use the most recent "
        f"{len(latencies_ms)} samples (maximum 10,000)."
    )
    for key in QUEUE_KEYS:
        print(f"Final {key}: {final_metrics.get(key)}")
    print(f"Capture running at end: {final_metrics.get('capture_running')}")
    if stats["failed"]:
        print(
            f"Failed requests: {stats['failed']}; "
            f"first errors: {errors}"
        )

    violations = []
    if attempted == 0 or successful != attempted:
        violations.append(f"only {successful}/{attempted} completed requests succeeded")

    if deltas["http_dropped_request_count"] != drop_reason_total:
        violations.append(
            "aggregate HTTP dropped-request count does not equal "
            "the sum of reason-specific counters"
        )

    if deltas["http_dropped_request_count"] != 0:
        violations.append(
            "HTTP correlator dropped "
            f"{deltas['http_dropped_request_count']} requests "
            f"(expired={deltas['http_expired_request_count']}, "
            f"capacity_evicted={deltas['http_capacity_evicted_request_count']}, "
            f"connection_closed={deltas['http_connection_closed_request_count']})"
        )

    if request_residual != 0:
        violations.append(
            f"HTTP request accounting residual is {request_residual}"
        )

    if response_residual != 0:
        violations.append(
            f"HTTP response accounting residual is {response_residual}"
        )

    if pending_delta > 0:
        violations.append(
            f"HTTP pending requests increased by {pending_delta}"
        )

    if (
        deltas["persistence_persisted_count"]
        != deltas["transaction_processing_count"]
    ):
        violations.append(
            "persisted transaction delta does not equal processed "
            "transaction delta after drain"
        )

    for key in (
        "rejected_packet_count",
        "dropped_packet_count",
        "tcp_stream_limit_rejection_count",
        "tcp_reassembly_buffer_overflow_count",
        "persistence_failed_count",
        "persistence_rejected_count",
    ):
        if deltas[key] != 0:
            violations.append(f"{key} increased by {deltas[key]}")

    if final_metrics.get("capture_running") is not True:
        violations.append("capture_running is not true at the end")

    for key in QUEUE_KEYS:
        if int(final_metrics.get(key, 0) or 0) != 0:
            violations.append(f"{key} did not drain to zero")

    if rss_growth_mib > args.max_rss_growth_mib:
        violations.append(
            f"RSS growth {rss_growth_mib:.1f}MiB exceeds "
            f"{args.max_rss_growth_mib:.1f}MiB"
        )

    if violations:
        print("LIVE CAPTURE SOAK TEST: FAIL")
        for violation in violations:
            print(" - " + violation)
        return 1

    print("LIVE CAPTURE SOAK TEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
