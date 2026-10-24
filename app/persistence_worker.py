import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass

from app.transaction_correlator import HTTPTransaction
from app.transaction_store import TransactionStore

logger = logging.getLogger(__name__)

PERSISTENCE_QUEUE_MAX_SIZE = 1000
QUEUE_WAIT_SAMPLE_CAPACITY = 10_000


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
            logger.error(
                "Persistence queue full; transaction rejected "
                "(rejected_count=%d)",
                self.rejected_count,
            )
            return False

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

    async def run(self, stop_event: asyncio.Event) -> None:
        """Persist jobs until shutdown is requested and the queue is drained."""
        while not stop_event.is_set() or not self.queue.empty():
            try:
                job = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=0.25,
                )
            except asyncio.TimeoutError:
                continue

            self._record_queue_wait_ns(
                time.perf_counter_ns() - job.enqueued_at_ns
            )

            try:
                await asyncio.to_thread(
                    self.store.save,
                    job.transaction,
                )
                self.persisted_count += 1
            except Exception:
                self.failed_count += 1
                logger.exception(
                    "Failed to persist queued HTTP transaction "
                    "(failed_count=%d)",
                    self.failed_count,
                )
            finally:
                self.queue.task_done()
