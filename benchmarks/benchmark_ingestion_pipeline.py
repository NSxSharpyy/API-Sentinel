#!/usr/bin/env python3
"""Synthetic HTTP ingest benchmark with serialization and memory accounting.

This exercises the application parser/correlator/serializer path with a sink
that discards messages after serialization. It does not measure eBPF capture,
ring-buffer loss, production ZeroMQ delivery, database writes, or line rate.
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
import tracemalloc
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.http_pipeline import HTTPMessagePipeline
from app.message_broker import serialize_http_message

REQUEST_DIRECTION = "TCP|198.51.100.10:49152->198.51.100.20:8080"
RESPONSE_DIRECTION = "TCP|198.51.100.20:8080->198.51.100.10:49152"
REQUEST = (
    b"GET /api/v1/items?page=1 HTTP/1.1\r\n"
    b"Host: benchmark.example\r\n"
    b"Accept: application/json\r\n\r\n"
)
RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: application/json\r\n"
    b"Content-Length: 11\r\n\r\n"
    b'{"ok":true}'
)


class SerializingDiscardPublisher:
    """Measure JSON serialization without retaining messages or using ZMQ."""

    def __init__(self) -> None:
        self.event_count = 0
        self.serialized_bytes = 0

    def publish(self, message) -> None:
        payload = serialize_http_message(message)
        self.event_count += 1
        self.serialized_bytes += len(payload)


def percentile(values: list[int], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index] / 1_000_000  # ms


def run(iterations: int, warmup: int) -> None:
    publisher = SerializingDiscardPublisher()
    pipeline = HTTPMessagePipeline(publisher)

    for _ in range(warmup):
        pipeline.feed(REQUEST, connection_id=REQUEST_DIRECTION)
        pipeline.feed(RESPONSE, connection_id=RESPONSE_DIRECTION)
    publisher.event_count = 0
    publisher.serialized_bytes = 0

    per_transaction_ns: deque[int] = deque(maxlen=min(iterations, 10_000))
    tracemalloc.start()
    start_ns = time.perf_counter_ns()
    for _ in range(iterations):
        item_start = time.perf_counter_ns()
        pipeline.feed(REQUEST, connection_id=REQUEST_DIRECTION)
        pipeline.feed(RESPONSE, connection_id=RESPONSE_DIRECTION)
        per_transaction_ns.append(time.perf_counter_ns() - item_start)
    elapsed_ns = time.perf_counter_ns() - start_ns
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    seconds = elapsed_ns / 1_000_000_000
    print("API-Sentinel synthetic HTTP ingestion benchmark")
    print("Boundary: HTTP parse -> correlation -> JSON serialization/discard")
    print("Excluded: eBPF capture, TCP ring-buffer reader, ZeroMQ network delivery, DB I/O")
    print(f"Iterations: {iterations}; warm-up transactions: {warmup}")
    print(f"Completed transactions: {len(pipeline.completed_transactions)} retained in bounded history")
    print(f"Published message events: {publisher.event_count} (expected {iterations * 2})")
    print(f"Serialized payload bytes: {publisher.serialized_bytes}")
    print(f"Throughput: {iterations / seconds:.1f} transactions/s; {publisher.event_count / seconds:.1f} events/s")
    print(f"Per-transaction p50: {percentile(list(per_transaction_ns), 0.50):.4f} ms")
    print(f"Per-transaction p95: {percentile(list(per_transaction_ns), 0.95):.4f} ms")
    print(f"Per-transaction p99: {percentile(list(per_transaction_ns), 0.99):.4f} ms")
    print(f"Traced current memory after run: {current_bytes / 1024:.1f} KiB")
    print(f"Traced peak memory during run: {peak_bytes / 1024:.1f} KiB")
    print(f"Completed history capacity: {pipeline.completed_transactions.maxlen}")
    if publisher.event_count != iterations * 2:
        raise SystemExit("ERROR: unexpected publication count")
    if pipeline.correlator.pending_request_count != 0:
        raise SystemExit("ERROR: unpaired requests remain after benchmark")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--warmup", type=int, default=1_000)
    args = parser.parse_args()
    if args.iterations <= 0 or args.warmup < 0:
        parser.error("--iterations must be positive and --warmup non-negative")
    run(args.iterations, args.warmup)
