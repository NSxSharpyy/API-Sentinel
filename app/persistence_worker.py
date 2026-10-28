import asyncio
import inspect
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass

from app.transaction_correlator import HTTPTransaction
from app.transaction_store import TransactionStore

logger = logging.getLogger(__name__)

def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


PERSISTENCE_QUEUE_MAX_SIZE = _positive_int_env(
    "API_SENTINEL_PERSISTENCE_QUEUE_MAX_SIZE", 12000
)
QUEUE_WAIT_SAMPLE_CAPACITY = 10_000
PERSISTENCE_DURATION_SAMPLE_CAPACITY = 10_000
PERSISTENCE_BATCH_MAX_SIZE = _positive_int_env(
    "API_SENTINEL_PERSISTENCE_BATCH_MAX_SIZE", 32
)


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
        batch_max_size: int | None = None,
    ) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        if batch_max_size is None:
            batch_max_size = PERSISTENCE_BATCH_MAX_SIZE
        if batch_max_size <= 0:
            raise ValueError("batch_max_size must be positive")

        self.store = store
        self.batch_max_size = batch_max_size
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

        # Track actual submissions to the store's batch API.
        self.batch_attempt_count = 0
        self.batch_attempted_job_count = 0
        self.batch_success_count = 0
        self.batch_successful_job_count = 0
        self.batch_failure_count = 0
        self.max_observed_batch_size = 0
        self._batch_size_samples: deque[int] = deque(
            maxlen=PERSISTENCE_DURATION_SAMPLE_CAPACITY
        )

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

    def _record_batch_attempt(self, batch_size: int) -> None:
        """Record a real submission to save_batch/save_batch_async."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.batch_attempt_count += 1
        self.batch_attempted_job_count += batch_size
        self.max_observed_batch_size = max(
            self.max_observed_batch_size, batch_size
        )
        self._batch_size_samples.append(batch_size)

    def _record_batch_success(self, batch_size: int) -> None:
        """Record a batch result with one duration per submitted job."""
        self.batch_success_count += 1
        self.batch_successful_job_count += batch_size

    def _record_batch_failure(self) -> None:
        """Record a failed batch call or invalid duration count."""
        self.batch_failure_count += 1

    @property
    def average_batch_size(self) -> float:
        """Lifetime average size of batches submitted to the store."""
        if self.batch_attempt_count == 0:
            return 0.0
        return self.batch_attempted_job_count / self.batch_attempt_count

    @property
    def p95_batch_size(self) -> float:
        """Nearest-rank p95 of the recent bounded batch-size sample."""
        if not self._batch_size_samples:
            return 0.0
        samples = sorted(self._batch_size_samples)
        index = max(0, math.ceil(0.95 * len(samples)) - 1)
        return float(samples[index])

    @property
    def batch_size_sample_count(self) -> int:
        """Number of batch-size samples retained for recent statistics."""
        return len(self._batch_size_samples)

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
        """Batch safe jobs; preserve ordered saves for BOLA-sensitive routes."""
        transactions = [job.transaction for job in jobs]
        store_type = type(self.store)
        supports_batch = (
            callable(getattr(store_type, "can_batch", None))
            and callable(getattr(store_type, "save_batch", None))
        )
        if supports_batch and self.store.can_batch(transactions):
            self._record_batch_attempt(len(jobs))
            try:
                durations = self.store.save_batch(transactions)
            except Exception:
                self._record_batch_failure()
                logger.exception(
                    "Batched persistence failed; retrying jobs individually"
                )
                return [
                    self._measure_store_call(job.transaction)
                    for job in jobs
                ]

            if len(durations) != len(jobs):
                self._record_batch_failure()
                raise RuntimeError(
                    "save_batch duration count does not match job count"
                )
            self._record_batch_success(len(jobs))
            return [(duration, None) for duration in durations]

        return [
            self._measure_store_call(job.transaction)
            for job in jobs
        ]


    async def _measure_async_store_call(
        self, transaction: HTTPTransaction
    ) -> tuple[int, Exception | None]:
        """Measure one awaited async-store call without blocking the event loop."""
        started_ns = time.perf_counter_ns()
        error = None
        try:
            await self.store.save_async(transaction)
        except Exception as exc:
            error = exc
        return time.perf_counter_ns() - started_ns, error

    async def _measure_async_batch_store_calls(
        self, jobs: list[PersistenceJob]
    ) -> list[tuple[int, Exception | None]]:
        """Batch safe async writes and keep BOLA-sensitive writes ordered."""
        transactions = [job.transaction for job in jobs]
        store_type = type(self.store)
        supports_batch = (
            callable(getattr(store_type, "can_batch", None))
            and callable(getattr(store_type, "save_batch_async", None))
        )

        if supports_batch and self.store.can_batch(transactions):
            self._record_batch_attempt(len(jobs))
            try:
                durations = await self.store.save_batch_async(transactions)
            except Exception:
                self._record_batch_failure()
                logger.exception(
                    "Async batched persistence failed; retrying jobs individually"
                )
                results = []
                for job in jobs:
                    results.append(
                        await self._measure_async_store_call(job.transaction)
                    )
                return results

            # Do not retry a potentially committed batch because its metrics
            # result is malformed; retrying could create duplicate records.
            if len(durations) != len(jobs):
                self._record_batch_failure()
                raise RuntimeError(
                    "save_batch_async duration count does not match job count"
                )

            self._record_batch_success(len(jobs))
            return [(duration, None) for duration in durations]

        # Process sequentially: BOLA-sensitive transactions must preserve order.
        results = []
        for job in jobs:
            results.append(
                await self._measure_async_store_call(job.transaction)
            )
        return results

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
            while len(jobs) < self.batch_max_size:
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
                async_save = getattr(type(self.store), "save_async", None)
                if inspect.iscoroutinefunction(async_save):
                    persistence_task = asyncio.create_task(
                        self._measure_async_batch_store_calls(jobs)
                    )
                else:
                    persistence_task = asyncio.create_task(
                        asyncio.to_thread(self._measure_batch_store_calls, jobs)
                    )

                try:
                    results = await asyncio.shield(persistence_task)
                except asyncio.CancelledError:
                    # Finish started database work before acknowledging queue jobs.
                    cancelled = True
                    results = await persistence_task

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
