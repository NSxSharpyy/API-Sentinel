#!/usr/bin/env python3
"""File-backed SQLite persistence and queue benchmark.

This uses the real SQLAlchemy TransactionStore and a temporary SQLite file.
It records a finite controlled workload and does not claim production database
performance or sustained eBPF ingestion line rate.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base
from app.http_reassembly import HTTPMessage
from app.models import TransactionLog
from app.persistence_worker import TransactionPersistenceWorker
from app.transaction_correlator import HTTPTransaction
from app.transaction_store import TransactionStore


def make_transaction(index: int) -> HTTPTransaction:
    now = datetime.now(timezone.utc)
    request_direction = f"TCP|192.0.2.10:{40000 + index % 20000}->192.0.2.20:8080"
    response_direction = f"TCP|192.0.2.20:8080->192.0.2.10:{40000 + index % 20000}"
    request = HTTPMessage(
        version="HTTP/1.1",
        headers={"host": "sqlite-benchmark.example", "accept": "application/json"},
        body=b"",
        message_type="request",
        method="GET",
        uri=f"/benchmark/items/{index}",
        connection_id=request_direction,
        captured_at=now,
    )
    response = HTTPMessage(
        version="HTTP/1.1",
        headers={"content-type": "application/json"},
        body=b'{"ok":true}',
        message_type="response",
        status_code=200,
        reason_phrase="OK",
        connection_id=response_direction,
        captured_at=now,
    )
    return HTTPTransaction(
        connection_key=f"TCP|192.0.2.10:{40000 + index % 20000}<->192.0.2.20:8080",
        request=request,
        response=response,
    )


def percentile(values: list[int], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index] / 1_000_000


async def _create_worker(folder: str, capacity: int):
    db_path = Path(folder) / "benchmark.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    store = TransactionStore(session_factory=sessions)
    worker = TransactionPersistenceWorker(store, max_queue_size=capacity)
    return engine, sessions, worker


async def _finish_case(engine, sessions, worker, stop_event, worker_task, started_ns, result):
    await asyncio.wait_for(worker.queue.join(), timeout=120.0)
    stop_event.set()
    await asyncio.wait_for(worker_task, timeout=120.0)
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000

    with sessions() as session:
        row_count = session.scalar(select(func.count()).select_from(TransactionLog)) or 0

    result.update({
        "rejected_total": worker.rejected_count,
        "persisted": worker.persisted_count,
        "failed": worker.failed_count,
        "db_rows": row_count,
        "queue_wait_samples": worker.queue_wait_sample_count,
        "avg_queue_wait_ms": worker.average_queue_wait_ms,
        "p95_queue_wait_ms": worker.p95_queue_wait_ms,
        "max_queue_wait_ms": worker.max_queue_wait_ms,
        "elapsed_ms": elapsed_ms,
    })
    engine.dispose()
    return result


async def run_burst_case(items: int, capacity: int, attempted: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="api-sentinel-sqlite-bench-") as folder:
        engine, sessions, worker = await _create_worker(folder, capacity)
        worker_logger = logging.getLogger("app.persistence_worker")
        original_level = worker_logger.level
        started = time.perf_counter_ns()
        accepted = 0
        try:
            if attempted > capacity:
                worker_logger.setLevel(logging.CRITICAL)
            for index in range(attempted):
                accepted += int(worker.enqueue(make_transaction(index)))
        finally:
            worker_logger.setLevel(original_level)
        initial_queue_depth = worker.queue.qsize()
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(worker.run(stop_event))
        result = {
            "attempted": attempted,
            "accepted": accepted,
            "initial_queue_depth": initial_queue_depth,
        }
        return await _finish_case(
            engine, sessions, worker, stop_event, worker_task, started, result
        )


async def run_sustained_case(items: int, capacity: int, producer_delay_ms: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="api-sentinel-sqlite-bench-") as folder:
        engine, sessions, worker = await _create_worker(folder, capacity)
        worker_logger = logging.getLogger("app.persistence_worker")
        original_level = worker_logger.level
        started = time.perf_counter_ns()
        accepted = 0
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(worker.run(stop_event))
        try:
            # Start the consumer first, then pace a finite producer against the
            # real file-backed SQLite store and bounded asyncio queue.
            worker_logger.setLevel(logging.CRITICAL)
            for index in range(items):
                accepted += int(worker.enqueue(make_transaction(index)))
                if producer_delay_ms > 0:
                    await asyncio.sleep(producer_delay_ms / 1000)
                else:
                    await asyncio.sleep(0)
        finally:
            worker_logger.setLevel(original_level)
        result = {
            "attempted": items,
            "accepted": accepted,
            "producer_delay_ms": producer_delay_ms,
            "queue_capacity": capacity,
        }
        return await _finish_case(
            engine, sessions, worker, stop_event, worker_task, started, result
        )


async def main(items: int, repeats: int, queue_capacity: int, producer_delay_ms: float) -> None:
    print("API-Sentinel file-backed SQLite persistence benchmark")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print("Database: temporary file-backed SQLite via SQLAlchemy TransactionStore")
    print("Measures: queue wait + transaction persistence; not PostgreSQL or production load")
    print(f"Items={items}; repeats={repeats}; queue_capacity={queue_capacity}; producer_delay_ms={producer_delay_ms}")

    for repeat in range(1, repeats + 1):
        burst = await run_burst_case(items=items, capacity=queue_capacity, attempted=items)
        print(f"\nRun {repeat}: preloaded burst")
        for key, value in burst.items():
            print(f"  {key}: {value}")
        if burst["failed"] or burst["persisted"] != burst["db_rows"]:
            raise SystemExit("ERROR: persistence failures or row-count mismatch in burst case")

        saturated = await run_burst_case(
            items=items,
            capacity=queue_capacity,
            attempted=max(items * 2, queue_capacity + 1),
        )
        print(f"\nRun {repeat}: bounded queue saturation")
        for key, value in saturated.items():
            print(f"  {key}: {value}")
        if saturated["failed"] or saturated["persisted"] != saturated["db_rows"]:
            raise SystemExit("ERROR: persistence failures or row-count mismatch in saturation case")

        sustained = await run_sustained_case(
            items=items,
            capacity=queue_capacity,
            producer_delay_ms=producer_delay_ms,
        )
        print(f"\nRun {repeat}: concurrent paced producer-consumer")
        for key, value in sustained.items():
            print(f"  {key}: {value}")
        if sustained["failed"] or sustained["persisted"] != sustained["db_rows"]:
            raise SystemExit("ERROR: persistence failures or row-count mismatch in sustained case")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--queue-capacity", type=int, default=100)
    parser.add_argument("--producer-delay-ms", type=float, default=0.2)
    args = parser.parse_args()
    if args.items <= 0 or args.repeats <= 0 or args.queue_capacity <= 0:
        parser.error("items, repeats, and queue-capacity must be positive")
    if args.producer_delay_ms < 0:
        parser.error("producer-delay-ms must be non-negative")
    asyncio.run(main(args.items, args.repeats, args.queue_capacity, args.producer_delay_ms))
