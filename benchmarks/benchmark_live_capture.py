#!/usr/bin/env python3
"""Controlled loopback load benchmark for the live API-Sentinel capture pipeline.

Requires the real WSL eBPF producer/ring-buffer reader and FastAPI app to be
running, with capture attached to loopback. This is a controlled loopback test,
not a physical-NIC line-rate benchmark. It uses only unauthenticated GET / and
GET /queue-status requests and never submits a BOLA trigger.
"""
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


def percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    position = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * p)))
    return ordered[position]


def get_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": "api-sentinel-live-capture-benchmark/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"GET {url} did not return a JSON object")
    return payload


def read_rss_kib(pid: int) -> int | None:
    status = Path(f"/proc/{pid}/status")
    try:
        for line in status.read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    return None


def discover_uvicorn_pids() -> list[int]:
    matches = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            command_line = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
        except (FileNotFoundError, PermissionError):
            continue
        if b"uvicorn" in command_line and b"app.main:app" in command_line:
            matches.append(int(entry.name))
    return sorted(set(matches))


def aggregate_rss_kib(pids: list[int]) -> int | None:
    values = [read_rss_kib(pid) for pid in pids]
    valid = [value for value in values if value is not None]
    return sum(valid) if valid else None


def hit_root(base_url: str, timeout: float) -> tuple[bool, float, str | None]:
    started = time.perf_counter_ns()
    try:
        payload = get_json(base_url.rstrip("/") + "/", timeout)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return payload.get("status") == "running", elapsed_ms, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return False, elapsed_ms, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--drain-timeout", type=float, default=20.0)
    parser.add_argument("--max-rss-growth-mib", type=float, default=128.0)
    parser.add_argument(
        "--pid", type=int, action="append", dest="pids",
        help="Uvicorn PID to sample; repeat for parent/worker processes. Auto-discovery is used if omitted.",
    )
    args = parser.parse_args()

    if args.requests <= 0 or args.concurrency <= 0 or args.timeout <= 0:
        parser.error("requests, concurrency and timeout must be positive")
    if args.drain_timeout <= 0 or args.max_rss_growth_mib < 0:
        parser.error("drain-timeout must be positive and max-rss-growth-mib non-negative")

    pids = sorted(set(args.pids or discover_uvicorn_pids()))
    if not pids:
        parser.error("Could not find Uvicorn PID. Pass --pid <PID> for app.main:app.")
    initial_rss = aggregate_rss_kib(pids)
    if initial_rss is None:
        parser.error(f"Could not read RSS for selected PID(s): {pids}")

    base_url = args.base_url.rstrip("/")
    try:
        baseline = get_json(base_url + "/queue-status", args.timeout)
    except Exception as exc:
        parser.error(f"API-Sentinel queue-status is not reachable: {exc}")

    if baseline.get("capture_running") is not True:
        parser.error("Capture supervisor is not reporting capture_running=true; start the real WSL capture path first.")

    baseline_counts = {key: int(baseline.get(key, 0) or 0) for key in COUNTER_KEYS}
    rss_samples: list[int] = [initial_rss]
    rss_stop = threading.Event()

    def sample_rss() -> None:
        while not rss_stop.wait(0.05):
            value = aggregate_rss_kib(pids)
            if value is not None:
                rss_samples.append(value)

    monitor = threading.Thread(target=sample_rss, name="api-sentinel-rss-sampler", daemon=True)
    monitor.start()
    latencies_ms: list[float] = []
    successful = 0
    failures: list[str] = []
    started = time.perf_counter()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(hit_root, base_url, args.timeout) for _ in range(args.requests)]
            for future in concurrent.futures.as_completed(futures):
                ok, elapsed_ms, error = future.result()
                latencies_ms.append(elapsed_ms)
                if ok:
                    successful += 1
                elif error:
                    failures.append(error)
    finally:
        elapsed_s = time.perf_counter() - started
        # Capture is on loopback: polling queue-status during drain creates
        # additional captured transactions. Use a quiet, bounded drain window,
        # then take one final metrics snapshot.
        time.sleep(args.drain_timeout)
        try:
            final_metrics = get_json(base_url + "/queue-status", args.timeout)
        except Exception:
            final_metrics = None
        rss_stop.set()
        monitor.join(timeout=1.0)

    if final_metrics is None:
        print("FAIL: unable to retrieve final /queue-status metrics")
        return 2
    required_metrics = set(COUNTER_KEYS) | {
        "capture_running",
        "raw_packet_queue",
        "header_queue",
        "metadata_queue",
        "persistence_queue_size",
    }

    missing_metrics = sorted(required_metrics - final_metrics.keys())
    if missing_metrics:
        print(
            "FAIL: final /queue-status response missing required metrics: "
            + ", ".join(missing_metrics)
        )
        return 2

    final_counts = {key: int(final_metrics.get(key, 0) or 0) for key in COUNTER_KEYS}
    deltas = {key: final_counts[key] - baseline_counts[key] for key in COUNTER_KEYS}
    rss_values_mib = [value / 1024 for value in rss_samples]
    rss_growth_mib = (max(rss_samples) - initial_rss) / 1024 if rss_samples else 0.0
    persisted_delta = deltas["persistence_persisted_count"]
    http_rate = successful / elapsed_s if elapsed_s > 0 else 0.0
    total_elapsed_s = time.perf_counter() - started

    print("API-Sentinel live loopback capture benchmark")
    print(f"Boundary: real HTTP client -> loopback capture -> ring reader -> queues -> HTTP parser/correlator -> persistence")
    print("Not a physical NIC line-rate or production-database benchmark.")
    print(f"URL: {base_url}/; requested={args.requests}; successful HTTP responses={successful}; concurrency={args.concurrency}")
    print(f"Load wall time: {elapsed_s:.3f}s; total test+drain time={total_elapsed_s:.3f}s")
    print(f"Successful HTTP response rate: {http_rate:.1f}/s; observed persisted delta={persisted_delta}")
    print(f"Request latency p50={percentile(latencies_ms, .50):.3f}ms; p95={percentile(latencies_ms, .95):.3f}ms; p99={percentile(latencies_ms, .99):.3f}ms")
    print("Counter deltas:")
    for key, value in deltas.items():
        print(f"  {key}: {value}")
    print(f"RSS baseline={initial_rss / 1024:.1f}MiB; sampled peak={max(rss_values_mib):.1f}MiB; sampled growth={rss_growth_mib:.1f}MiB")
    print(f"Raw queue depth at end={final_metrics.get('raw_packet_queue')}; persistence queue depth={final_metrics.get('persistence_queue_size')}; capture_running={final_metrics.get('capture_running')}")
    if failures:
        print(f"HTTP failures: {len(failures)}; first errors: {failures[:5]}")

    violations = []
    if successful != args.requests:
        violations.append(f"only {successful}/{args.requests} HTTP requests succeeded")
    if persisted_delta < successful:
        violations.append(f"persisted only {persisted_delta} transactions for {successful} successful requests within drain timeout")
    for key in ("rejected_packet_count", "dropped_packet_count", "tcp_stream_limit_rejection_count", "tcp_reassembly_buffer_overflow_count", "persistence_failed_count", "persistence_rejected_count"):
        if deltas[key] != 0:
            violations.append(f"{key} increased by {deltas[key]}")
    if final_metrics.get("capture_running") is not True:
        violations.append("capture_running became false")
    for queue_key in (
        "raw_packet_queue",
        "header_queue",
        "metadata_queue",
        "persistence_queue_size",
    ):
        depth = int(final_metrics.get(queue_key, 0) or 0)
        if depth != 0:
            violations.append(
                f"{queue_key} did not drain to zero (final_depth={depth})"
            )
    if rss_growth_mib > args.max_rss_growth_mib:
        violations.append(f"sampled RSS grew by {rss_growth_mib:.1f} MiB (limit {args.max_rss_growth_mib:.1f} MiB)")

    if violations:
        print("LIVE CAPTURE BENCHMARK: FAIL")
        for item in violations:
            print(f" - {item}")
        return 1
    print("LIVE CAPTURE BENCHMARK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
