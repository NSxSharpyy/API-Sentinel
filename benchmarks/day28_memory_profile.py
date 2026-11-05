#!/usr/bin/env python3
"""Generate controlled HTTP traffic for the API-Sentinel Day 28 memory profile."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid

from datetime import datetime, timezone
from pathlib import Path


BASE_ENDPOINTS = (
    "/healthz",
    "/",
    "/api/v1/endpoints",
    "/api/v1/alerts",
    "/detection-status",
    "/blocklist-status",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_record(stream, record: dict) -> None:
    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    stream.flush()


def hit_endpoint(base_url: str, endpoint: str, timeout: float):
    started = time.perf_counter()

    try:
        request = urllib.request.Request(
            base_url.rstrip("/") + endpoint,
            headers={"User-Agent": "api-sentinel-day28-load/1.0"},
        )

        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")

            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise RuntimeError("Response exceeded 1 MB safety limit")

        return True, (time.perf_counter() - started) * 1000, None

    except Exception as exc:
        return (
            False,
            (time.perf_counter() - started) * 1000,
            f"{type(exc).__name__}: {exc}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--requests-per-second", type=float, default=1.0)
    parser.add_argument(
        "--sample-interval",
        type=int,
        default=60,
        help="Interval for writing workload progress records; no HTTP polling",
    )
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument(
        "--output",
        default="artifacts/day28_workload.jsonl",
        help="Separate JSONL file for workload statistics",
    )
    args = parser.parse_args()

    if (
        args.duration_seconds <= 0
        or args.requests_per_second <= 0
        or args.sample_interval <= 0
        or args.timeout <= 0
    ):
        parser.error("All durations, rates, and timeouts must be positive")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    run_id = str(uuid.uuid4())
    base_url = args.base_url.rstrip("/")
    request_interval = 1.0 / args.requests_per_second

    successful = 0
    failed = 0
    latency_total_ms = 0.0
    latency_max_ms = 0.0
    last_error = None
    endpoint_index = 0
    interrupted = False

    started = time.monotonic()
    next_request = started
    next_sample = started + args.sample_interval

    print(f"Run ID: {run_id}")
    print(f"Workload output: {output}")
    print(f"Duration: {args.duration_seconds}s")
    print(f"Target request rate: {args.requests_per_second}/second")
    print("Monitoring HTTP requests: disabled")
    print("Starting controlled live-capture workload.")

    with output.open("a", encoding="utf-8") as stream:
        write_record(stream, {
            "type": "run_start",
            "run_id": run_id,
            "timestamp_utc": utc_now(),
            "duration_seconds": args.duration_seconds,
            "target_requests_per_second": args.requests_per_second,
            "progress_interval_seconds": args.sample_interval,
            "endpoints": list(BASE_ENDPOINTS),
        })

        try:
            while time.monotonic() - started < args.duration_seconds:
                now = time.monotonic()

                if now < next_request:
                    time.sleep(next_request - now)

                now = time.monotonic()
                if now - started >= args.duration_seconds:
                    break

                endpoint = BASE_ENDPOINTS[
                    endpoint_index % len(BASE_ENDPOINTS)
                ]
                endpoint_index += 1

                ok, latency, error = hit_endpoint(
                    base_url, endpoint, args.timeout
                )

                latency_total_ms += latency
                latency_max_ms = max(latency_max_ms, latency)

                if ok:
                    successful += 1
                else:
                    failed += 1
                    last_error = error

                next_request += request_interval

                # Avoid catch-up bursts after a slow request.
                now = time.monotonic()
                if next_request < now:
                    next_request = now

                if now >= next_sample:
                    elapsed = now - started
                    attempted = successful + failed
                    average_latency = (
                        latency_total_ms / attempted if attempted else 0.0
                    )

                    record = {
                        "type": "workload_sample",
                        "run_id": run_id,
                        "timestamp_utc": utc_now(),
                        "elapsed_seconds": round(elapsed, 2),
                        "successful_requests": successful,
                        "failed_requests": failed,
                        "average_request_latency_ms": round(
                            average_latency, 3
                        ),
                        "max_request_latency_ms": round(
                            latency_max_ms, 3
                        ),
                        "achieved_requests_per_second": round(
                            attempted / elapsed if elapsed else 0.0, 3
                        ),
                        "last_error": last_error,
                    }
                    write_record(stream, record)

                    print(
                        f"elapsed={elapsed:.0f}s "
                        f"success={successful} failed={failed} "
                        f"avg_latency_ms={average_latency:.2f}"
                    )

                    next_sample = now + args.sample_interval

        except KeyboardInterrupt:
            interrupted = True
            print("\nInterrupted. Stopping workload generation.")

        elapsed = time.monotonic() - started
        attempted = successful + failed
        average_latency = (
            latency_total_ms / attempted if attempted else 0.0
        )

        summary = {
            "type": "run_end",
            "run_id": run_id,
            "timestamp_utc": utc_now(),
            "load_elapsed_seconds": round(elapsed, 2),
            "interrupted": interrupted,
            "successful_requests": successful,
            "failed_requests": failed,
            "average_request_latency_ms": round(average_latency, 3),
            "max_request_latency_ms": round(latency_max_ms, 3),
            "achieved_requests_per_second": round(
                attempted / elapsed if elapsed else 0.0, 3
            ),
            "last_error": last_error,
            "queue_drain_status": "not_checked",
            "memory_analysis_status": "see in-process profiler JSONL",
        }
        write_record(stream, summary)

    print("\nDay 28 workload summary")
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Successful requests: {successful}")
    print(f"Failed requests: {failed}")
    print(f"Average latency: {average_latency:.2f} ms")
    print(f"Maximum latency: {latency_max_ms:.2f} ms")
    print(f"Achieved rate: {attempted / elapsed if elapsed else 0:.3f}/s")
    print(f"Workload output: {output}")

    print("\nWorkload generation has stopped.")
    print("Now press Ctrl+C in the Uvicorn terminal.")
    print("The application will stop capture, drain both queues,")
    print("and write its final in-process memory-profile records.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
