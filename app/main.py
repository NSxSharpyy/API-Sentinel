
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import queues
from app.capture_supervisor import supervise_capture
from app.config import settings
from app.http_pipeline import HTTPMessagePipeline
from app.message_broker import HTTPTransactionPublisher
from app.packet_worker import packet_worker
from app.persistence_worker import TransactionPersistenceWorker
from app.queues import header_queue, metadata_queue, raw_packet_queue
from app.transaction_store import TransactionStore, initialize_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistence and start packet capture services."""
    stop_event = asyncio.Event()
    persistence_stop_event = asyncio.Event()

    # Initialize SQLAlchemy tables before starting background services.
    initialize_database()

    publisher = HTTPTransactionPublisher()
    transaction_store = TransactionStore()
    persistence_worker = TransactionPersistenceWorker(transaction_store)

    # Use the background worker so database writes do not block
    # the packet-processing event loop.
    pipeline = HTTPMessagePipeline(
        publisher=publisher,
        persistence_worker=persistence_worker,
    )

    app.state.stop_event = stop_event
    app.state.http_pipeline = pipeline
    app.state.http_publisher = publisher
    app.state.transaction_store = transaction_store
    app.state.persistence_worker = persistence_worker
    app.state.capture_status = "starting"

    def update_capture_status(status: str) -> None:
        app.state.capture_status = status

    persistence_task = asyncio.create_task(
        persistence_worker.run(persistence_stop_event),
        name="api-sentinel-persistence-worker",
    )
    app.state.persistence_worker_task = persistence_task

    worker_task = asyncio.create_task(
        packet_worker(pipeline, stop_event),
        name="api-sentinel-packet-worker",
    )
    app.state.packet_worker_task = worker_task

    reader_command = [
        "sudo",
        "-n",
        "/usr/local/sbin/api-sentinel-ring-reader",
    ]

    capture_task = asyncio.create_task(
        supervise_capture(
            reader_command,
            stop_event,
            on_status=update_capture_status,
        ),
        name="api-sentinel-capture-supervisor",
    )
    app.state.capture_task = capture_task

    logger.info("API-Sentinel persistence worker started")
    logger.info("API-Sentinel packet worker started")
    logger.info("API-Sentinel capture supervisor started")

    try:
        yield
    finally:
        # First stop packet capture and the packet-processing worker.
        stop_event.set()
        capture_task.cancel()

        try:
            await capture_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "Capture supervisor failed during shutdown"
            )

        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(
                "Packet worker did not stop within 5 seconds; cancelling"
            )
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "Packet worker failed while being cancelled"
                )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "Packet worker failed during shutdown"
            )

        # No more transactions should be enqueued now.
        # Signal the persistence worker to drain its remaining queue.
        persistence_stop_event.set()

        try:
            await persistence_task
        except asyncio.CancelledError:
            logger.warning("Persistence worker was cancelled")
        except Exception:
            logger.exception(
                "Persistence worker failed during shutdown"
            )
        finally:
            publisher.close()

        logger.info("API-Sentinel background services stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "running",
    }

@app.get("/queue-status")
async def queue_status():
    capture_task = getattr(app.state, "capture_task", None)
    capture_status = getattr(app.state, "capture_status", "stopped")

    return {
        "raw_packet_queue": raw_packet_queue.qsize(),
        "header_queue": header_queue.qsize(),
        "metadata_queue": metadata_queue.qsize(),
        "accepted_packet_count": queues.accepted_packet_count,
        "rejected_packet_count": queues.rejected_packet_count,
        "dropped_packet_count": queues.dropped_packet_count,
        "capture_running": (
            capture_status == "running"
            and capture_task is not None
            and not capture_task.done()
        ),
    }
