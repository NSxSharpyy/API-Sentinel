
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


def test_worker_uses_batch_save_when_store_supports_safe_batch():
    async def run_test():
        class BatchStore:
            def __init__(self):
                self.batches = []

            def can_batch(self, transactions):
                return True

            def save_batch(self, transactions):
                self.batches.append(list(transactions))
                return [1_000_000 for _ in transactions]

            def save(self, transaction):
                raise AssertionError("save_batch should have been used")

        store = BatchStore()
        worker = TransactionPersistenceWorker(store=store)
        first = make_transaction()
        second = make_transaction()
        worker.enqueue(first)
        worker.enqueue(second)

        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert store.batches == [[first, second]]
        assert worker.persisted_count == 2
        assert worker.failed_count == 0
        assert worker.queue.empty()

    asyncio.run(run_test())


def test_worker_falls_back_to_individual_saves_when_batch_fails(caplog):
    async def run_test():
        class FallbackStore:
            def __init__(self):
                self.batch_attempts = 0
                self.saved = []

            def can_batch(self, transactions):
                return True

            def save_batch(self, transactions):
                self.batch_attempts += 1
                raise RuntimeError("synthetic batch failure")

            def save(self, transaction):
                self.saved.append(transaction)

        store = FallbackStore()
        worker = TransactionPersistenceWorker(store=store)
        first = make_transaction()
        second = make_transaction()
        worker.enqueue(first)
        worker.enqueue(second)

        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert store.batch_attempts == 1
        assert store.saved == [first, second]
        assert worker.persisted_count == 2
        assert worker.failed_count == 0
        assert worker.queue.empty()
        assert "retrying jobs individually" in caplog.text

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



def test_async_worker_uses_async_batch_save():
    async def run_test():
        class AsyncBatchStore:
            def __init__(self):
                self.batches = []

            def can_batch(self, transactions):
                return True

            async def save_batch_async(self, transactions):
                self.batches.append(list(transactions))
                return [1_000_000 for _ in transactions]

            async def save_async(self, transaction):
                raise AssertionError("safe batch should use save_batch_async")

        store = AsyncBatchStore()
        worker = TransactionPersistenceWorker(store=store)
        first = make_transaction()
        second = make_transaction()
        worker.enqueue(first)
        worker.enqueue(second)

        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert store.batches == [[first, second]]
        assert worker.persisted_count == 2
        assert worker.failed_count == 0
        assert worker.queue.empty()

    asyncio.run(run_test())


def test_async_worker_falls_back_to_individual_saves_when_batch_fails(caplog):
    async def run_test():
        class AsyncFallbackStore:
            def __init__(self):
                self.batch_attempts = 0
                self.saved = []

            def can_batch(self, transactions):
                return True

            async def save_batch_async(self, transactions):
                self.batch_attempts += 1
                raise RuntimeError("synthetic async batch failure")

            async def save_async(self, transaction):
                self.saved.append(transaction)

        store = AsyncFallbackStore()
        worker = TransactionPersistenceWorker(store=store)
        first = make_transaction()
        second = make_transaction()
        worker.enqueue(first)
        worker.enqueue(second)

        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert store.batch_attempts == 1
        assert store.saved == [first, second]
        assert worker.persisted_count == 2
        assert worker.failed_count == 0
        assert worker.queue.empty()
        assert "retrying jobs individually" in caplog.text

    asyncio.run(run_test())


def test_async_worker_keeps_non_batchable_transactions_ordered():
    async def run_test():
        class OrderedAsyncStore:
            def __init__(self):
                self.saved = []

            def can_batch(self, transactions):
                return False

            async def save_batch_async(self, transactions):
                raise AssertionError("non-batchable work must remain individual")

            async def save_async(self, transaction):
                self.saved.append(transaction)

        store = OrderedAsyncStore()
        worker = TransactionPersistenceWorker(store=store)
        first = make_transaction()
        second = make_transaction()
        worker.enqueue(first)
        worker.enqueue(second)

        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert store.saved == [first, second]
        assert worker.persisted_count == 2
        assert worker.failed_count == 0

    asyncio.run(run_test())



def test_async_worker_does_not_retry_batch_on_bad_duration_count(caplog):
    async def run_test():
        class BadDurationStore:
            def __init__(self):
                self.batch_attempts = 0
                self.individual_saves = []

            def can_batch(self, transactions):
                return True

            async def save_batch_async(self, transactions):
                self.batch_attempts += 1
                # Simulate a committed batch with malformed metrics output.
                return [1_000_000]

            async def save_async(self, transaction):
                self.individual_saves.append(transaction)

        store = BadDurationStore()
        worker = TransactionPersistenceWorker(store=store)
        worker.enqueue(make_transaction())
        worker.enqueue(make_transaction())

        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(worker.run(stop_event), timeout=2)

        assert store.batch_attempts == 1
        assert store.individual_saves == []
        assert worker.persisted_count == 0
        assert worker.failed_count == 2
        assert worker.queue.empty()
        assert "duration count does not match" in caplog.text

    asyncio.run(run_test())
