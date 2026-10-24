#!/usr/bin/env python3
"""Repeatable baseline benchmark for HTTP message JSON serialization."""

from __future__ import annotations

import argparse
import math
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns

# Allow this script to run directly from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.http_reassembly import HTTPMessage
from app.message_broker import serialize_http_message


BODY_SIZES = (0, 1024, 8192, 32768)


def percentile(values: list[int], percent: float) -> int:
    """Return the nearest-rank percentile from nanosecond samples."""
    ordered = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(ordered)) - 1)
    return ordered[index]


def make_message(body_size: int) -> HTTPMessage:
    """Build one stable representative request for repeated serialization."""
    pattern = bytes(range(256))
    body = pattern * (body_size // len(pattern)) + pattern[:body_size % 256]

    headers = {
        "host": "api.example.test",
        "user-agent": "API-Sentinel-Serialization-Benchmark/1.0",
        "accept": "application/json",
        "content-type": "application/octet-stream",
        "content-length": str(body_size),
        "x-request-id": "serialization-baseline-001",
    }

    is_empty = body_size == 0
    return HTTPMessage(
        version="HTTP/1.1",
        headers=headers,
        body=body,
        message_type="request",
        method="GET" if is_empty else "POST",
        uri="/health" if is_empty else "/api/v1/events",
        connection_id="TCP|192.0.2.10:49152->192.0.2.20:8000",
        captured_at=datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc),
    )


def run_case(
    body_size: int,
    iterations: int,
    repeats: int,
    warmup: int,
) -> None:
    message = make_message(body_size)

    # Confirm the serializer works and calculate output size outside timing.
    payload_size = len(serialize_http_message(message))

    for _ in range(warmup):
        serialize_http_message(message)

    all_samples_ns: list[int] = []
    total_wall_ns = 0

    print(f"\n--- Request body: {body_size:,} bytes ---")
    print(f"Serialized payload: {payload_size:,} bytes")

    for run_number in range(1, repeats + 1):
        samples_ns: list[int] = []
        batch_start_ns = perf_counter_ns()

        for _ in range(iterations):
            started_ns = perf_counter_ns()
            serialize_http_message(message)
            samples_ns.append(perf_counter_ns() - started_ns)

        wall_ns = perf_counter_ns() - batch_start_ns
        total_wall_ns += wall_ns
        all_samples_ns.extend(samples_ns)

        median_us = statistics.median(samples_ns) / 1_000
        p95_us = percentile(samples_ns, 95) / 1_000
        throughput = iterations / (wall_ns / 1_000_000_000)

        print(
            f"Run {run_number}: "
            f"median={median_us:.3f} us, "
            f"p95={p95_us:.3f} us, "
            f"wall={wall_ns / 1_000_000:.2f} ms, "
            f"throughput={throughput:,.0f} calls/s"
        )

    overall_median_us = statistics.median(all_samples_ns) / 1_000
    overall_p95_us = percentile(all_samples_ns, 95) / 1_000
    overall_throughput = (
        iterations * repeats / (total_wall_ns / 1_000_000_000)
    )

    print(
        f"Aggregate: median={overall_median_us:.3f} us, "
        f"p95={overall_p95_us:.3f} us, "
        f"throughput={overall_throughput:,.0f} calls/s"
    )
    print(
        "Sub-millisecond p95: "
        + ("PASS" if overall_p95_us < 1_000 else "NOT MET")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark HTTP message serialization latency."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2000,
        help="Measured serializations per run (default: 2000)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Measured runs per payload size (default: 5)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=300,
        help="Warm-up calls per payload size (default: 300)",
    )
    args = parser.parse_args()

    if args.iterations < 1 or args.repeats < 1 or args.warmup < 0:
        parser.error("iterations/repeats must be positive; warmup cannot be negative")

    print("API-Sentinel HTTP serialization baseline")
    print(f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.platform()}")
    print(f"Iterations per run: {args.iterations:,}")
    print(f"Repeats: {args.repeats}")
    print(f"Warm-up calls per payload size: {args.warmup:,}")
    print("Measurement: serialize_http_message() call only")
    print("Excluded: parsing, queue wait, ZeroMQ send, and database persistence")
    print("Per-call timings include performance-clock measurement overhead.")

    for body_size in BODY_SIZES:
        run_case(body_size, args.iterations, args.repeats, args.warmup)


if __name__ == "__main__":
    main()
