
import asyncio
import logging
import os
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

    initialize_database()

    publisher = HTTPTransactionPublisher()
    transaction_store = TransactionStore()
    persistence_worker = TransactionPersistenceWorker(transaction_store)

    pipeline = HTTPMessagePipeline(
        publisher=publisher,
        persistence_worker=persistence_worker,
    )

    # Keep kernel synchronization opt-in. Opening the map also validates its ABI.
    blocklist_enabled = os.getenv(
        "API_SENTINEL_BLOCKLIST_SYNC_ENABLED", ""
    ).strip().lower() in {"1", "true", "yes"}
    blocklist_writer = None
    blocklist_synchronizer = None
    blocklist_task = None
    blocklist_stop_event = asyncio.Event()

    if blocklist_enabled:
        try:
            from app.blocklist_map_writer import LibbpfBlocklistMapWriter
            from app.blocklist_sync import BlocklistSynchronizer

            blocklist_writer = LibbpfBlocklistMapWriter()
            blocklist_synchronizer = BlocklistSynchronizer(
                queues.blocklist_verdict_queue,
                blocklist_writer,
            )
        except Exception:
            publisher.close()
            logger.exception(
                "Blocklist synchronization requested but initialization failed"
            )
            raise

    app.state.blocklist_sync_enabled = blocklist_enabled
    app.state.blocklist_synchronizer = blocklist_synchronizer
    app.state.blocklist_sync_task = None

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
        "/usr/local/sbin/api-sentinel-ring-reader-day16",
        "/sys/fs/bpf/api_sentinel_day16_events",
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

    if blocklist_synchronizer is not None:
        blocklist_task = asyncio.create_task(
            blocklist_synchronizer.run(blocklist_stop_event),
            name="api-sentinel-blocklist-sync-worker",
        )
        app.state.blocklist_sync_task = blocklist_task

    logger.info("API-Sentinel persistence worker started")
    if blocklist_task is not None:
        logger.info("API-Sentinel blocklist synchronization worker started")
    logger.info("API-Sentinel packet worker started")
    logger.info("API-Sentinel capture supervisor started")

    try:
        yield
    finally:
        # Stop capture and packet processing first.
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

        # Stop blocklist synchronization and drain any queued verdicts.
        if blocklist_task is not None:
            blocklist_stop_event.set()
            try:
                await asyncio.wait_for(blocklist_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Blocklist worker did not stop within 5 seconds; cancelling"
                )
                blocklist_task.cancel()
                try:
                    await blocklist_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Blocklist worker failed during shutdown")
            finally:
                if blocklist_writer is not None:
                    try:
                        blocklist_writer.close()
                    except Exception:
                        logger.exception("Failed to close blocklist map writer")

        # Drain queued database writes after packet processing stops.
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
    persistence_worker = getattr(
        app.state, "persistence_worker", None
    )
    persistence_task = getattr(
        app.state, "persistence_worker_task", None
    )
    pipeline = getattr(app.state, "http_pipeline", None)

    return {
        "raw_packet_queue": raw_packet_queue.qsize(),
        "header_queue": header_queue.qsize(),
        "metadata_queue": metadata_queue.qsize(),
        "persistence_queue_size": (
            persistence_worker.queue.qsize()
            if persistence_worker is not None
            else 0
        ),
        "persistence_persisted_count": (
            persistence_worker.persisted_count
            if persistence_worker is not None
            else 0
        ),
        "persistence_failed_count": (
            persistence_worker.failed_count
            if persistence_worker is not None
            else 0
        ),
        "persistence_rejected_count": (
            persistence_worker.rejected_count
            if persistence_worker is not None
            else 0
        ),
        "persistence_worker_running": (
            persistence_task is not None
            and not persistence_task.done()
        ),
        "http_completed_transaction_count": (
            len(pipeline.completed_transactions)
            if pipeline is not None
            else 0
        ),
"transaction_processing_count": (
    pipeline.transaction_processing_count
    if pipeline is not None
    else 0
),
"last_transaction_processing_latency_ms": (
    pipeline.last_transaction_processing_latency_ms
    if pipeline is not None
    else 0.0
),
"average_transaction_processing_latency_ms": (
    pipeline.average_transaction_processing_latency_ms
    if pipeline is not None
    else 0.0
),
"max_transaction_processing_latency_ms": (
    pipeline.max_transaction_processing_latency_ms
    if pipeline is not None
    else 0.0
),
        "capture_to_publish_count": (
            pipeline.capture_to_publish_count
            if pipeline is not None else 0
        ),
        "last_capture_to_publish_latency_ms": (
            pipeline.last_capture_to_publish_latency_ms
            if pipeline is not None else 0.0
        ),
        "average_capture_to_publish_latency_ms": (
            pipeline.average_capture_to_publish_latency_ms
            if pipeline is not None else 0.0
        ),
        "max_capture_to_publish_latency_ms": (
            pipeline.max_capture_to_publish_latency_ms
            if pipeline is not None else 0.0
        ),
        "http_pending_request_count": (
            pipeline.correlator.pending_request_count
            if pipeline is not None
            else 0
        ),
        "http_unmatched_response_count": (
            pipeline.correlator.unmatched_responses
            if pipeline is not None
            else 0
        ),
        "http_open_connection_count": (
            pipeline.open_connections
            if pipeline is not None
            else 0
        ),
        "accepted_packet_count": queues.accepted_packet_count,
        "accepted_tcp_event_count": queues.accepted_tcp_event_count,
        "accepted_udp_event_count": queues.accepted_udp_event_count,
        "rejected_packet_count": queues.rejected_packet_count,
        "dropped_packet_count": queues.dropped_packet_count,
        "tcp_stream_limit_rejection_count": (
            queues.tcp_stream_limit_rejection_count
        ),
        "tcp_reassembly_buffer_overflow_count": (
            queues.tcp_reassembly_buffer_overflow_count
        ),
        "tcp_packets_processed_count": (
            queues.tcp_packets_processed_count
        ),
        "tcp_syn_packets_count": queues.tcp_syn_packets_count,
        "tcp_payload_packets_count": queues.tcp_payload_packets_count,
        "tcp_payload_bytes_count": queues.tcp_payload_bytes_count,
        "tcp_packets_without_stream_count": (
            queues.tcp_packets_without_stream_count
        ),
        "tcp_payload_delivered_to_http_count": (
            queues.tcp_payload_delivered_to_http_count
        ),
        "tcp_payload_bytes_delivered_to_http_count": (
            queues.tcp_payload_bytes_delivered_to_http_count
        ),
        "capture_running": (
            capture_status == "running"
            and capture_task is not None
            and not capture_task.done()
        ),
    }


@app.get("/debug/http-parsers")
async def debug_http_parsers():
    pipeline = getattr(app.state, "http_pipeline", None)

    if pipeline is None:
        return {"error": "HTTP pipeline is not initialized"}

    return {
        "parser_count": len(pipeline._parsers),
        "parsers": [
            {
                "buffered_bytes": len(parser.buffer),
                "pending_head_responses": parser.pending_head_responses,
            }
            for parser in pipeline._parsers.values()
        ],
        "parsed_request_count": pipeline.parsed_request_count,
        "parsed_response_count": pipeline.parsed_response_count,
        "completed_transactions": len(
            pipeline.completed_transactions
        ),
        "pending_requests": pipeline.correlator.pending_request_count,
        "unmatched_responses": pipeline.correlator.unmatched_responses,
        "tcp_stream_diagnostics": getattr(
            queues,
            "tcp_stream_diagnostics",
            {
                "active_streams": 0,
                "reported_streams": 0,
                "streams": [],
            },
        ),
    }

@app.get("/detection-status")
async def detection_status():
    """Expose lab-scoped BOLA detection and latency metrics."""
    store = getattr(app.state, "transaction_store", None)
    detector = getattr(store, "bola_detector", None)
    if detector is None:
        return {
            "status": "not_initialized",
            "bola_detection_count": 0,
            "capture_to_detection_count": 0,
        }
    return {"status": "running", **detector.snapshot()}


@app.get("/blocklist-status")
async def blocklist_status():
    """Expose blocklist queue and synchronization worker diagnostics."""
    enabled = getattr(app.state, "blocklist_sync_enabled", False)
    synchronizer = getattr(app.state, "blocklist_synchronizer", None)
    task = getattr(app.state, "blocklist_sync_task", None)

    if not enabled:
        status = "disabled"
    elif synchronizer is None:
        status = "not_initialized"
    elif task is not None and not task.done():
        status = "running"
    else:
        status = "stopped"

    response = {
        "status": status,
        "enabled": enabled,
        "queue_depth": queues.blocklist_verdict_queue.qsize(),
        "queue_capacity": queues.BLOCK_VERDICT_QUEUE_MAX_SIZE,
        "kernel_map_pin": "/sys/fs/bpf/api_sentinel_day17_blocklist",
        "packet_drop_enforcement_configured": False,
    }
    if synchronizer is not None:
        response.update(synchronizer.snapshot())
    return response

