"""Synthetic persistence queue burst test; does not use the project database."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Add the repository root so direct script execution can import app.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.persistence_worker import TransactionPersistenceWorker


class SyntheticStore:
    def __init__(self, delay_ms):
        self.delay_seconds = delay_ms / 1000

    def save(self, _event):
        if self.delay_seconds:
            time.sleep(self.delay_seconds)


async def run(args):
    worker = TransactionPersistenceWorker(
        store=SyntheticStore(args.store_delay_ms),
        max_queue_size=args.queue_capacity,
        batch_max_size=args.batch_size,
    )
    stop_event = asyncio.Event()
    task = asyncio.create_task(worker.run(stop_event))
    await asyncio.sleep(0)

    accepted = rejected = 0
    started = time.perf_counter()

    for i in range(args.events):
        if worker.enqueue({"synthetic_event_id": i}):
            accepted += 1
        else:
            rejected += 1

        if (i + 1) % args.burst_size == 0:
            await asyncio.sleep(args.burst_pause_ms / 1000)

    stop_event.set()
    await task
    elapsed = time.perf_counter() - started

    result = {
        "offered": args.events,
        "accepted": accepted,
        "rejected": rejected,
        "persisted": worker.persisted_count,
        "failed": worker.failed_count,
        "queue_capacity": args.queue_capacity,
        "observed_max_queue_depth": worker.max_queue_depth,
        "batch_size": args.batch_size,
        "simulated_store_delay_ms": args.store_delay_ms,
        "elapsed_seconds": round(elapsed, 4),
        "offered_events_per_second": round(args.events / elapsed, 2),
        "persisted_events_per_second": round(
            worker.persisted_count / elapsed, 2
        ),
    }
    print(json.dumps(result, indent=2))

    assert accepted + rejected == args.events, "offered-event accounting mismatch"
    assert worker.max_queue_depth <= args.queue_capacity, "queue exceeded capacity"
    assert accepted == worker.persisted_count + worker.failed_count, (
        "accepted-event accounting mismatch"
    )
    assert worker.failed_count == 0, "synthetic persistence failures occurred"

    print("DAY 20 QUEUE BURST INVARIANTS: PASS")


def positive_int(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=positive_int, default=10000)
    parser.add_argument("--queue-capacity", type=positive_int, default=512)
    parser.add_argument("--batch-size", type=positive_int, default=32)
    parser.add_argument("--store-delay-ms", type=float, default=0.1)
    parser.add_argument("--burst-size", type=positive_int, default=500)
    parser.add_argument("--burst-pause-ms", type=float, default=1.0)
    args = parser.parse_args()

    if args.store_delay_ms < 0 or args.burst_pause_ms < 0:
        parser.error("delay values cannot be negative")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
