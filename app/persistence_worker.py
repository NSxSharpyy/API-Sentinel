import asyncio
import logging
from dataclasses import dataclass

from app.transaction_correlator import HTTPTransaction
from app.transaction_store import TransactionStore

logger = logging.getLogger(__name__)

PERSISTENCE_QUEUE_MAX_SIZE = 1000


@dataclass(frozen=True)
class PersistenceJob:
    transaction: HTTPTransaction


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

    def enqueue(self, transaction: HTTPTransaction) -> bool:
        """Queue a transaction without blocking the event loop."""
        try:
            self.queue.put_nowait(PersistenceJob(transaction))
        except asyncio.QueueFull:
            self.rejected_count += 1
            logger.error(
                "Persistence queue full; transaction rejected "
                "(rejected_count=%d)",
                self.rejected_count,
            )
            return False

        return True

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
