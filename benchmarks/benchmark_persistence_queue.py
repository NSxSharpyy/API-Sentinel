#!/usr/bin/env python3
"""Controlled burst benchmark for persistence queue wait time.

Uses a synthetic store. It does not measure real database performance.
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.persistence_worker import TransactionPersistenceWorker


class SyntheticStore:
    """Simulate consumer work without accessing the database."""

    def __init__(self, delay_ms: float):
        self.delay_seconds = delay_ms / 1000

    def save(self, _transaction):
        if self.delay_seconds:
            time.sleep(self.delay_seconds)


async def run_case(
    label: str,
    attempted: int,
    capacity: int,
    service_delay_ms: float,
):
    worker = TransactionPersistenceWorker(
        store=SyntheticStore(service_delay_ms),
        max_queue_size=capacity,
    )

    # Suppress expected full-queue warnings only during saturation setup.
    worker_logger = logging.getLogger("app.persistence_worker")
    original_level = worker_logger.level
    try:
        if attempted > capacity:
            worker_logger.setLevel(logging.CRITICAL)
        accepted = sum(
            worker.enqueue({"synthetic_id": i})
            for i in range(attempted)
        )
    finally:
        worker_logger.setLevel(original_level)
    initial_depth = worker.queue.qsize()

    stop_event = asyncio.Event()
    stop_event.set()

    started_ns = time.perf_counter_ns()
    await worker.run(stop_event)
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000

    print(f"\n{label}")
    print(f"  attempted:             {attempted}")
    print(f"  accepted:              {accepted}")
    print(f"  initially queued:      {initial_depth}")
    print(f"  rejected:              {worker.rejected_count}")
    print(f"  persisted (synthetic): {worker.persisted_count}")
    print(f"  failed:                {worker.failed_count}")
    print(f"  simulated save delay:  {service_delay_ms:.3f} ms")
    print(f"  queue wait samples:    {worker.queue_wait_sample_count}")
    print(f"  average queue wait:    {worker.average_queue_wait_ms:.3f} ms")
    print(f"  p95 queue wait:        {worker.p95_queue_wait_ms:.3f} ms")
    print(f"  maximum queue wait:    {worker.max_queue_wait_ms:.3f} ms")
    print(f"  total drain time:      {elapsed_ms:.3f} ms")


async def main(items: int, repeats: int):
    print("API-Sentinel persistence queue burst audit")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print("Clock: time.perf_counter_ns()")
    print("Boundary: enqueue timestamp to worker dequeue")
    print("Consumer starts after the burst is enqueued.")
    print("Synthetic store only; no real database I/O.")
    print(f"Items per normal burst: {items}; repetitions: {repeats}")

    for repeat in range(1, repeats + 1):
        await run_case(
            f"Run {repeat}: immediate synthetic save",
            attempted=items,
            capacity=items,
            service_delay_ms=0,
        )
        await run_case(
            f"Run {repeat}: 0.5 ms simulated save",
            attempted=items,
            capacity=items,
            service_delay_ms=0.5,
        )
        await run_case(
            f"Run {repeat}: full-queue rejection",
            attempted=items * 2,
            capacity=items,
            service_delay_ms=0.5,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    if args.items <= 0 or args.repeats <= 0:
        parser.error("--items and --repeats must be positive")

    asyncio.run(main(args.items, args.repeats))
