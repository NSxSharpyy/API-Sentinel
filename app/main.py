from fastapi import FastAPI

from app.config import settings
from app.queues import (
    header_queue,
    metadata_queue,
    raw_packet_queue,
)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "running",
        "day": 1,
    }


@app.get("/queue-status")
async def queue_status():
    return {
        "raw_packet_queue": raw_packet_queue.qsize(),
        "header_queue": header_queue.qsize(),
        "metadata_queue": metadata_queue.qsize(),
    }