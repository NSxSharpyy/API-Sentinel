
import asyncio
from unittest.mock import Mock

import pytest

from app.persistence_worker import TransactionPersistenceWorker


def make_transaction():
    return Mock()


def test_enqueue_accepts_transaction():
    async def run_test():
        worker = TransactionPersistenceWorker(
            store=Mock(),
            max_queue_size=1,
        )
        transaction = make_transaction()

        assert worker.enqueue(transaction) is True
        assert worker.queue.qsize() == 1
        assert worker.rejected_count == 0

    asyncio.run(run_test())


def test_enqueue_counts_rejected_transaction_when_queue_is_full():
    async def run_test():
        worker = TransactionPersistenceWorker(
            store=Mock(),
            max_queue_size=1,
        )

        assert worker.enqueue(make_transaction()) is True
        assert worker.enqueue(make_transaction()) is False
        assert worker.queue.qsize() == 1
        assert worker.rejected_count == 1
        # Rejected items were never dequeued, so they add no wait observation.
        assert worker.queue_wait_count == 0

    asyncio.run(run_test())


def test_worker_persists_queued_transaction_and_drains_on_shutdown():
    async def run_test():
        store = Mock()
        worker = TransactionPersistenceWorker(store=store)
        transaction = make_transaction()
        stop_event = asyncio.Event()

        assert worker.enqueue(transaction) is True
        stop_event.set()

        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        store.save.assert_called_once_with(transaction)
        assert worker.persisted_count == 1
        assert worker.failed_count == 0
        assert worker.queue.empty()
        assert worker.queue_wait_count == 1
        assert worker.queue_wait_sample_count == 1
        assert worker.last_queue_wait_ms >= 0
        assert worker.average_queue_wait_ms >= 0
        assert worker.max_queue_wait_ms >= worker.last_queue_wait_ms
        assert worker.p95_queue_wait_ms >= 0

    asyncio.run(run_test())


def test_worker_continues_after_persistence_failure(caplog):
    async def run_test():
        store = Mock()
        store.save.side_effect = RuntimeError("database unavailable")
        worker = TransactionPersistenceWorker(store=store)
        stop_event = asyncio.Event()

        worker.enqueue(make_transaction())
        stop_event.set()

        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert worker.failed_count == 1
        assert worker.persisted_count == 0
        assert worker.queue.empty()
        # Queue wait is recorded even when the later database save fails.
        assert worker.queue_wait_count == 1
        assert worker.queue_wait_sample_count == 1
        assert "Failed to persist queued HTTP transaction" in caplog.text

    asyncio.run(run_test())


def test_queue_wait_metrics_aggregate_and_report_recent_p95():
    worker = TransactionPersistenceWorker(store=Mock())

    worker._record_queue_wait_ns(1_000_000)
    worker._record_queue_wait_ns(2_000_000)
    worker._record_queue_wait_ns(3_000_000)

    assert worker.queue_wait_count == 3
    assert worker.queue_wait_sample_count == 3
    assert worker.last_queue_wait_ms == pytest.approx(3.0)
    assert worker.average_queue_wait_ms == pytest.approx(2.0)
    assert worker.max_queue_wait_ms == pytest.approx(3.0)
    assert worker.p95_queue_wait_ms == pytest.approx(3.0)
