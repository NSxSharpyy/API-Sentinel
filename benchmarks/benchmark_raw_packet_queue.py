#!/usr/bin/env python3
"""Measure raw-packet enqueue-to-dequeue wait with a preloaded synthetic burst."""

import argparse
import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import Mock

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.packet_worker as worker_module
from app import queues
from app.ring_buffer_consumer import consume_events


async def synthetic_events(count: int):
    captured_at = datetime.now(timezone.utc)
    for index in range(count):
        yield {
            "packet_id": f"raw-queue-bench-{index}",
            "captured_at": captured_at,
            "payload": b"synthetic-queue-measurement",
            "source_ip": "192.0.2.10",
            "destination_ip": "192.0.2.20",
            "source_port": 40000 + (index % 20000),
            "destination_port": 9999,
            "protocol": "UDP",
            "tcp_flags": [],
        }


async def run_once(run_number: int, items: int):
    original_queue = queues.raw_packet_queue
    original_worker_queue = worker_module.raw_packet_queue
    original_metrics = queues.raw_packet_queue_wait_metrics

    counter_names = (
        "accepted_packet_count",
        "accepted_udp_event_count",
        "rejected_packet_count",
        "dropped_packet_count",
    )
    original_counters = {
        name: getattr(queues, name) for name in counter_names
    }

    test_queue = asyncio.Queue(maxsize=items)
    metrics = queues.QueueWaitMetrics(sample_capacity=items)
    queues.raw_packet_queue = test_queue
    worker_module.raw_packet_queue = test_queue
    queues.raw_packet_queue_wait_metrics = metrics

    stop_event = asyncio.Event()
    task = None

    try:
        stats = await consume_events(synthetic_events(items))
        if stats.accepted != items or stats.dropped or stats.rejected:
            raise RuntimeError(f"Unexpected producer stats: {stats!r}")

        initial_depth = test_queue.qsize()
        pipeline = Mock()

        start_ns = time.perf_counter_ns()
        task = asyncio.create_task(
            worker_module.packet_worker(pipeline, stop_event)
        )
        await asyncio.wait_for(test_queue.join(), timeout=10)
        drain_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        stop_event.set()
        await asyncio.wait_for(task, timeout=3)
        task = None

        result = metrics.snapshot()
        print(f"\nRun {run_number}: {items} packet preloaded burst")
        print(f"  producer accepted: {stats.accepted}")
        print(f"  initial queue depth: {initial_depth}")
        print(f"  dequeue samples: {result['queue_wait_sample_count']}")
        print(f"  average queue wait: {result['average_queue_wait_ms']:.3f} ms")
        print(f"  p95 queue wait: {result['p95_queue_wait_ms']:.3f} ms")
        print(f"  maximum queue wait: {result['max_queue_wait_ms']:.3f} ms")
        print(f"  total drain time: {drain_ms:.3f} ms")
        print("  pipeline feed calls:", pipeline.feed.call_count)

        if result["queue_wait_count"] != items:
            raise RuntimeError("Expected one wait sample per dequeued packet.")

    finally:
        if task is not None:
            stop_event.set()
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        queues.raw_packet_queue = original_queue
        worker_module.raw_packet_queue = original_worker_queue
        queues.raw_packet_queue_wait_metrics = original_metrics

        for name, value in original_counters.items():
            setattr(queues, name, value)


async def main(items: int, repeats: int):
    print("API-Sentinel raw packet queue-wait benchmark")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print("Boundary: ring-buffer consumer enqueue to packet-worker dequeue")
    print("Synthetic UDP packets; no capture, TCP parsing, or database I/O.")
    print("Workload: preloaded burst, not sustained production load.")

    for run_number in range(1, repeats + 1):
        await run_once(run_number, items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    if args.items <= 0 or args.repeats <= 0:
        parser.error("--items and --repeats must be positive")

    asyncio.run(main(args.items, args.repeats))
