import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import queues
from app.config import settings
from app.http_pipeline import HTTPMessagePipeline
from app.message_broker import HTTPTransactionPublisher
from app.packet_worker import packet_worker
from app.queues import (
    header_queue,
    metadata_queue,
    raw_packet_queue,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the packet worker at startup and stop it at shutdown."""
    stop_event = asyncio.Event()
    publisher = HTTPTransactionPublisher()
    pipeline = HTTPMessagePipeline(publisher=publisher)

    app.state.stop_event = stop_event
    app.state.http_pipeline = pipeline
    app.state.http_publisher = publisher

    worker_task = asyncio.create_task(
        packet_worker(pipeline, stop_event),
        name="api-sentinel-packet-worker",
    )
    app.state.packet_worker_task = worker_task

    logger.info("API-Sentinel packet worker started")

    try:
        yield
    finally:
        stop_event.set()

        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except asyncio.TimeoutError:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        finally:
            publisher.close()

        logger.info("API-Sentinel packet worker stopped")


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
    return {
        "raw_packet_queue": raw_packet_queue.qsize(),
        "header_queue": header_queue.qsize(),
        "metadata_queue": metadata_queue.qsize(),
        "dropped_packet_count": queues.dropped_packet_count,
    }