import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass

from app.transaction_correlator import HTTPTransaction
from app.transaction_store import TransactionStore

logger = logging.getLogger(__name__)

PERSISTENCE_QUEUE_MAX_SIZE = 12000
QUEUE_WAIT_SAMPLE_CAPACITY = 10_000
PERSISTENCE_DURATION_SAMPLE_CAPACITY = 10_000
PERSISTENCE_BATCH_MAX_SIZE = 32


@dataclass(frozen=True)
class PersistenceJob:
    transaction: HTTPTransaction
    enqueued_at_ns: int


class TransactionPersistenceWorker:
    """Persist queued HTTP transactions outside the event-loop thread."""

    def __init__(
        self,
        store: TransactionStore,
        max_queue_size: int = PERSISTENCE_QUEUE_MAX_SIZE,
    ) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")

        self.store = store
        self.queue: asyncio.Queue[PersistenceJob] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self.rejected_count = 0
        self.persisted_count = 0
        self.failed_count = 0

        # Lifetime counters/sums; p95 uses only the most recent bounded sample.
        self.queue_wait_count = 0
        self.total_queue_wait_ns = 0
        self.last_queue_wait_ms = 0.0
        self.max_queue_wait_ms = 0.0
        self._queue_wait_samples_ns: deque[int] = deque(
            maxlen=QUEUE_WAIT_SAMPLE_CAPACITY
        )
        self.max_queue_depth = 0

        self.batch_amortized_per_job_duration_count = 0
        self.total_batch_amortized_per_job_duration_ns = 0
        self.last_batch_amortized_per_job_duration_ms = 0.0
        self.max_batch_amortized_per_job_duration_ms = 0.0
        self._batch_amortized_per_job_duration_samples_ns: deque[int] = deque(
            maxlen=PERSISTENCE_DURATION_SAMPLE_CAPACITY
        )

        self.store_call_duration_count = 0
        self.total_store_call_duration_ns = 0
        self.max_store_call_duration_ms = 0.0
        self._store_call_duration_samples_ns: deque[int] = deque(
            maxlen=PERSISTENCE_DURATION_SAMPLE_CAPACITY
        )

    def enqueue(self, transaction: HTTPTransaction) -> bool:
        """Queue a transaction without blocking the event loop."""
        try:
            self.queue.put_nowait(
                PersistenceJob(
                    transaction=transaction,
                    enqueued_at_ns=time.perf_counter_ns(),
                )
            )
        except asyncio.QueueFull:
            self.rejected_count += 1

            # Preserve the exact rejection count without flooding the
            # event loop with a log write for every rejected transaction.
            if self.rejected_count == 1 or self.rejected_count % 1000 == 0:
                logger.error(
                    "Persistence queue full; transaction rejected "
                    "(rejected_count=%d; logging first and every 1000)",
                    self.rejected_count,
                )

            return False

        self.max_queue_depth = max(
            self.max_queue_depth, self.queue.qsize()
        )
        return True

    def _record_queue_wait_ns(self, elapsed_ns: int) -> None:
        """Record enqueue-to-dequeue wait; never store transaction contents."""
        elapsed_ns = max(0, elapsed_ns)
        elapsed_ms = elapsed_ns / 1_000_000

        self.queue_wait_count += 1
        self.total_queue_wait_ns += elapsed_ns
        self.last_queue_wait_ms = elapsed_ms
        self.max_queue_wait_ms = max(self.max_queue_wait_ms, elapsed_ms)
        self._queue_wait_samples_ns.append(elapsed_ns)

    @property
    def queue_wait_sample_count(self) -> int:
        """Number of samples currently retained for recent-window percentiles."""
        return len(self._queue_wait_samples_ns)

    @property
    def average_queue_wait_ms(self) -> float:
        """Lifetime average enqueue-to-dequeue wait in milliseconds."""
        if self.queue_wait_count == 0:
            return 0.0
        return (
            self.total_queue_wait_ns
            / self.queue_wait_count
            / 1_000_000
        )

    @property
    def p95_queue_wait_ms(self) -> float:
        """Nearest-rank p95 of the most recent bounded sample window."""
        if not self._queue_wait_samples_ns:
            return 0.0
        samples = sorted(self._queue_wait_samples_ns)
        index = max(0, math.ceil(0.95 * len(samples)) - 1)
        return samples[index] / 1_000_000

    def _record_batch_amortized_per_job_duration_ns(self, elapsed_ns: int) -> None:
        elapsed_ns = max(0, elapsed_ns)
        elapsed_ms = elapsed_ns / 1_000_000
        self.batch_amortized_per_job_duration_count += 1
        self.total_batch_amortized_per_job_duration_ns += elapsed_ns
        self.last_batch_amortized_per_job_duration_ms = elapsed_ms
        self.max_batch_amortized_per_job_duration_ms = max(
            self.max_batch_amortized_per_job_duration_ms, elapsed_ms
        )
        self._batch_amortized_per_job_duration_samples_ns.append(elapsed_ns)

    @property
    def average_batch_amortized_per_job_duration_ms(self) -> float:
        if self.batch_amortized_per_job_duration_count == 0:
            return 0.0
        return (
            self.total_batch_amortized_per_job_duration_ns
            / self.batch_amortized_per_job_duration_count
            / 1_000_000
        )

    @property
    def p95_batch_amortized_per_job_duration_ms(self) -> float:
        if not self._batch_amortized_per_job_duration_samples_ns:
            return 0.0
        samples = sorted(self._batch_amortized_per_job_duration_samples_ns)
        index = max(0, math.ceil(0.95 * len(samples)) - 1)
        return samples[index] / 1_000_000

    def _record_store_call_duration_ns(self, elapsed_ns: int) -> None:
        elapsed_ns = max(0, elapsed_ns)
        elapsed_ms = elapsed_ns / 1_000_000
        self.store_call_duration_count += 1
        self.total_store_call_duration_ns += elapsed_ns
        self.max_store_call_duration_ms = max(
            self.max_store_call_duration_ms, elapsed_ms
        )
        self._store_call_duration_samples_ns.append(elapsed_ns)

    @property
    def average_store_call_duration_ms(self) -> float:
        if self.store_call_duration_count == 0:
            return 0.0
        return (
            self.total_store_call_duration_ns
            / self.store_call_duration_count
            / 1_000_000
        )

    @property
    def p95_store_call_duration_ms(self) -> float:
        if not self._store_call_duration_samples_ns:
            return 0.0
        samples = sorted(self._store_call_duration_samples_ns)
        index = max(0, math.ceil(0.95 * len(samples)) - 1)
        return samples[index] / 1_000_000

    def _measure_store_call(
        self, transaction: HTTPTransaction
    ) -> tuple[int, Exception | None]:
        started_ns = time.perf_counter_ns()
        error = None
        try:
            self.store.save(transaction)
        except Exception as exc:
            error = exc
        elapsed_ns = time.perf_counter_ns() - started_ns
        return elapsed_ns, error

    def _measure_batch_store_calls(
        self, jobs: list[PersistenceJob]
    ) -> list[tuple[int, Exception | None]]:
        """Save jobs sequentially in one thread dispatch.

        Each store.save() still owns its existing transaction and commit.
        """
        return [
            self._measure_store_call(job.transaction)
            for job in jobs
        ]


    async def run(self, stop_event: asyncio.Event) -> None:
        """Persist jobs in small batches while preserving per-job commits."""
        while not stop_event.is_set() or not self.queue.empty():
            try:
                first_job = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=0.25,
                )
            except asyncio.TimeoutError:
                continue

            jobs = [first_job]
            while len(jobs) < PERSISTENCE_BATCH_MAX_SIZE:
                try:
                    jobs.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            for job in jobs:
                self._record_queue_wait_ns(
                    time.perf_counter_ns() - job.enqueued_at_ns
                )

            batch_started_ns = time.perf_counter_ns()
            cancelled = False

            try:
                thread_task = asyncio.create_task(
                    asyncio.to_thread(self._measure_batch_store_calls, jobs)
                )
                try:
                    results = await asyncio.shield(thread_task)
                except asyncio.CancelledError:
                    # Let already-started database work finish before marking
                    # its queue jobs done during shutdown.
                    cancelled = True
                    results = await thread_task

                batch_elapsed_ns = time.perf_counter_ns() - batch_started_ns
                amortized_elapsed_ns = batch_elapsed_ns // len(jobs)

                for job, (store_call_ns, save_error) in zip(jobs, results):
                    self._record_store_call_duration_ns(store_call_ns)
                    self._record_batch_amortized_per_job_duration_ns(amortized_elapsed_ns)

                    if save_error is None:
                        self.persisted_count += 1
                    else:
                        self.failed_count += 1
                        logger.error(
                            "Failed to persist queued HTTP transaction "
                            "(failed_count=%d)",
                            self.failed_count,
                            exc_info=(
                                type(save_error),
                                save_error,
                                save_error.__traceback__,
                            ),
                        )
            except Exception:
                self.failed_count += len(jobs)
                logger.exception(
                    "Unexpected persistence batch-dispatch failure "
                    "(failed_count=%d; batch_size=%d)",
                    self.failed_count,
                    len(jobs),
                )
            finally:
                for _job in jobs:
                    self.queue.task_done()

            if cancelled:
                raise asyncio.CancelledError
