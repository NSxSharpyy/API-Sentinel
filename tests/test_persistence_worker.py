
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
        assert "Failed to persist queued HTTP transaction" in caplog.text

    asyncio.run(run_test())
