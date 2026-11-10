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

    stop_load = threading.Event()
    stop_rss = threading.Event()
    data_lock = threading.Lock()
    latencies_ms: list[float] = []
    errors: list[str] = []
    stats = {"successful": 0}
    rss_samples = [initial_rss]

    def sample_rss() -> None:
        while not stop_rss.wait(0.05):
            value = aggregate_rss_kib(pids)
            if value is not None:
                rss_samples.append(value)

    def worker() -> None:
        while not stop_load.is_set():
            ok, latency, error = hit_root(base_url, args.timeout)
            with data_lock:
                latencies_ms.append(latency)
                if ok:
                    stats["successful"] += 1
                else:
                    errors.append(error or "root endpoint returned an unexpected result")

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

    required_keys = set(COUNTER_KEYS) | set(QUEUE_KEYS) | {"capture_running"}
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
    successful = stats["successful"]
    attempted = len(latencies_ms)
    rss_growth_mib = (max(rss_samples) - initial_rss) / 1024
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

    print(
        f"RSS baseline={initial_rss / 1024:.1f}MiB; "
        f"sampled peak={max(rss_samples) / 1024:.1f}MiB; "
        f"growth={rss_growth_mib:.1f}MiB"
    )
    for key in QUEUE_KEYS:
        print(f"Final {key}: {final_metrics.get(key)}")
    print(f"Capture running at end: {final_metrics.get('capture_running')}")
    if errors:
        print(f"Failed requests: {len(errors)}; first errors: {errors[:5]}")

    violations = []
    if attempted == 0 or successful != attempted:
        violations.append(f"only {successful}/{attempted} completed requests succeeded")
    if deltas["persistence_persisted_count"] < successful:
        violations.append("persisted record delta is lower than successful responses")

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
