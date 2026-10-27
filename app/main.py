
import asyncio
import logging
import os
from pathlib import Path
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app import queues
from app.capture_supervisor import supervise_capture
from app.alert_bus import AlertBus
from app.api_v1 import router as api_v1_router
from app.config import settings
from app.blocklist_verdicts import BlocklistVerdictProducer
from app.http_pipeline import HTTPMessagePipeline
from app.message_broker import HTTPTransactionPublisher
from app.packet_worker import packet_worker
from app.persistence_worker import TransactionPersistenceWorker
from app.queues import header_queue, metadata_queue, raw_packet_queue
from app.blocklist_drop_audit import (
    DROP_EVENTS_PIN,
    AsyncBlockedTransactionAuditStore,
    supervise_blocklist_drop_audit,
)
from app.async_transaction_store import (
    AsyncTransactionStore,
    initialize_async_database,
)
from app.database import async_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistence and start packet capture services."""
    drop_audit_enabled = os.getenv(
        "API_SENTINEL_BLOCKLIST_DROP_AUDIT_ENABLED", ""
    ).strip().lower() in {"1", "true", "yes"}
    drop_audit_reader = (
        Path(__file__).resolve().parent.parent
        / "ebpf-day17"
        / "blocklist_drop_reader"
    )
    if drop_audit_enabled and not drop_audit_reader.is_file():
        raise RuntimeError(
            "Day 19 audit reader is missing; build ebpf-day17/blocklist_drop_reader"
        )

    drop_audit_stop_event = asyncio.Event()
    drop_audit_task = None
    drop_audit_store = AsyncBlockedTransactionAuditStore()

    stop_event = asyncio.Event()
    persistence_stop_event = asyncio.Event()

    await initialize_async_database()

    publisher = HTTPTransactionPublisher()
    alert_bus = AlertBus()
    transaction_store = AsyncTransactionStore(alert_bus=alert_bus)
    persistence_worker = TransactionPersistenceWorker(transaction_store)

    pipeline = HTTPMessagePipeline(
        publisher=publisher,
        persistence_worker=persistence_worker,
    )

    # Keep kernel synchronization opt-in. Opening the map also validates its ABI.
    blocklist_enabled = os.getenv(
        "API_SENTINEL_BLOCKLIST_SYNC_ENABLED", ""
    ).strip().lower() in {"1", "true", "yes"}
    blocklist_policy_requested = os.getenv(
        "API_SENTINEL_BLOCKLIST_POLICY_ENABLED", ""
    ).strip().lower() in {"1", "true", "yes"}
    if blocklist_policy_requested and not blocklist_enabled:
        alert_bus.close()
        publisher.close()
        raise RuntimeError(
            "Blocklist policy requires API_SENTINEL_BLOCKLIST_SYNC_ENABLED=1"
        )
    blocklist_policy = None
    blocklist_sender = None
    blocklist_writer = None
    blocklist_synchronizer = None
    blocklist_receiver = None
    blocklist_task = None
    blocklist_receiver_task = None
    blocklist_producer = BlocklistVerdictProducer(
        queues.blocklist_verdict_queue,
        enabled=blocklist_enabled,
    )
    blocklist_stop_event = asyncio.Event()
    blocklist_receiver_stop_event = asyncio.Event()

    if blocklist_enabled:
        try:
            from app.blocklist_map_writer import LibbpfBlocklistMapWriter
            from app.blocklist_sync import BlocklistSynchronizer
            from app.blocklist_verdict_receiver import BlocklistVerdictReceiver

            blocklist_writer = LibbpfBlocklistMapWriter()
            # Configurable batch size; default favors lower burst latency.
            blocklist_batch_size = int(
                os.getenv("API_SENTINEL_BLOCKLIST_BATCH_SIZE", "5")
            )
            blocklist_synchronizer = BlocklistSynchronizer(
                queues.blocklist_verdict_queue,
                blocklist_writer,
                batch_size=blocklist_batch_size,
            )
            verdict_endpoint = os.getenv(
                "API_SENTINEL_BLOCKLIST_VERDICT_ENDPOINT",
                "tcp://127.0.0.1:5558",
            ).strip()
            # The receiver validates this as IPv4 loopback, so an accidental
            # non-loopback bind fails closed during application startup.
            blocklist_receiver = BlocklistVerdictReceiver(
                blocklist_producer,
                endpoint=verdict_endpoint,
            )
            if blocklist_policy_requested:
                raw_allowlist = os.getenv(
                    "API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS", ""
                )
                allowed_source_ips = [
                    item.strip() for item in raw_allowlist.split(",")
                    if item.strip()
                ]
                if not allowed_source_ips:
                    raise ValueError(
                        "Blocklist policy requires an exact allowlist in "
                        "API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS"
                    )
                from app.blocklist_policy import (
                    BlocklistPolicy, ThreadOwnedVerdictSender
                )
                from app.blocklist_verdict_client import BlocklistVerdictSender
                # Connect to the receiver's actual bound endpoint. This also
                # supports ephemeral loopback ports in controlled runtime tests.
                blocklist_sender = ThreadOwnedVerdictSender(
                    lambda: BlocklistVerdictSender(
                        endpoint=blocklist_receiver.endpoint
                    )
                )
                blocklist_policy = BlocklistPolicy(
                    blocklist_sender,
                    allowed_source_ips,
                    enabled=True,
                    ttl_seconds=int(os.getenv(
                        "API_SENTINEL_BLOCKLIST_VERDICT_TTL_SECONDS", "60"
                    )),
                )
        except Exception:
            if blocklist_sender is not None:
                blocklist_sender.close()
            if blocklist_receiver is not None:
                blocklist_receiver.close()
            if blocklist_writer is not None:
                blocklist_writer.close()
            alert_bus.close()
            publisher.close()
            logger.exception(
                "Blocklist synchronization requested but initialization failed"
            )
            raise

    transaction_store.blocklist_policy = blocklist_policy
    app.state.blocklist_policy = blocklist_policy
    app.state.blocklist_sender = blocklist_sender
    app.state.blocklist_sync_enabled = blocklist_enabled
    app.state.blocklist_synchronizer = blocklist_synchronizer
    app.state.blocklist_sync_task = None
    app.state.blocklist_verdict_producer = blocklist_producer
    app.state.blocklist_verdict_receiver = blocklist_receiver
    app.state.blocklist_verdict_receiver_task = None

    app.state.stop_event = stop_event
    app.state.http_pipeline = pipeline
    app.state.http_publisher = publisher
    app.state.transaction_store = transaction_store
    app.state.alert_bus = alert_bus
    app.state.persistence_worker = persistence_worker
    app.state.capture_status = "starting"
    app.state.blocked_transaction_audit_enabled = drop_audit_enabled
    app.state.blocked_transaction_audit_task = None

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

    if blocklist_receiver is not None:
        blocklist_receiver_task = asyncio.create_task(
            blocklist_receiver.run(blocklist_receiver_stop_event),
            name="api-sentinel-blocklist-verdict-receiver",
        )
        app.state.blocklist_verdict_receiver_task = blocklist_receiver_task

    logger.info("API-Sentinel persistence worker started")
    if blocklist_task is not None:
        logger.info("API-Sentinel blocklist synchronization worker started")
    if blocklist_receiver_task is not None:
        logger.info("API-Sentinel blocklist verdict receiver started")
    logger.info("API-Sentinel packet worker started")
    logger.info("API-Sentinel capture supervisor started")

    if drop_audit_enabled:
        drop_audit_task = asyncio.create_task(
            supervise_blocklist_drop_audit(
                ["sudo", "-n", str(drop_audit_reader), DROP_EVENTS_PIN],
                drop_audit_stop_event,
                drop_audit_store,
            ),
            name="api-sentinel-blocked-transaction-audit",
        )
        app.state.blocked_transaction_audit_task = drop_audit_task

    try:
        yield
    finally:
        # Stop the audit reader and reap its child process before shutdown.
        if drop_audit_task is not None:
            drop_audit_stop_event.set()
            try:
                await asyncio.wait_for(drop_audit_task, timeout=4.0)
            except asyncio.TimeoutError:
                drop_audit_task.cancel()
                try:
                    await drop_audit_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Day 19 drop-audit worker failed during shutdown")

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

        # Drain persistence first. Post-commit policy sends need the
        # verdict receiver and blocklist worker to remain alive.
        persistence_stop_event.set()
        try:
            await persistence_task
        except asyncio.CancelledError:
            logger.warning("Persistence worker was cancelled")
        except Exception:
            logger.exception("Persistence worker failed during shutdown")
        finally:
            alert_bus.close()
            publisher.close()

        # Allow locally submitted policy verdicts time to reach the receiver.
        if blocklist_policy is not None and blocklist_receiver is not None:
            expected = blocklist_policy.snapshot()["submitted_count"]
            deadline = asyncio.get_running_loop().time() + 2.0
            while (
                blocklist_receiver.snapshot()["receiver_messages_accepted"] < expected
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.02)
            accepted = blocklist_receiver.snapshot()["receiver_messages_accepted"]
            if accepted < expected:
                logger.warning(
                    "Timed out waiting for accepted verdicts: expected at least %d, accepted %d",
                    expected,
                    accepted,
                )

        # Stop verdict intake after persistence and sender calls have completed.
        if blocklist_receiver_task is not None:
            blocklist_receiver_stop_event.set()
            try:
                await asyncio.wait_for(blocklist_receiver_task, timeout=2.0)
            except asyncio.TimeoutError:
                blocklist_receiver_task.cancel()
                try:
                    await blocklist_receiver_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Blocklist verdict receiver failed during shutdown")
            finally:
                if blocklist_receiver is not None:
                    blocklist_receiver.close()

        # Stop synchronization only after receiver intake has completed.
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

        if blocklist_sender is not None:
            blocklist_sender.close()

        try:
            await async_engine.dispose()
        except Exception:
            logger.exception("Failed to dispose async database engine")

        logger.info("API-Sentinel background services stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(api_v1_router)


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """Stream committed security alerts to connected frontend clients.

    Alert delivery is best-effort and process-local. This endpoint should only
    be exposed on a trusted development network until authentication and
    authorization are implemented.
    """
    alert_bus = getattr(websocket.app.state, "alert_bus", None)
    if alert_bus is None:
        await websocket.close(code=1013, reason="Alert bus is not initialized")
        return
    try:
        subscriber = alert_bus.subscribe()
    except RuntimeError:
        await websocket.close(code=1013, reason="Alert bus is shutting down")
        return

    await websocket.accept()

    async def stream_alerts() -> None:
        # Poll the thread-safe queue without occupying a worker thread. This
        # also makes disconnect cancellation deterministic in async servers.
        while True:
            try:
                event = subscriber.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.025)
                continue
            await websocket.send_json(event.to_dict())

    async def watch_disconnect() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

    sender_task = asyncio.create_task(stream_alerts(), name="api-sentinel-ws-alert-sender")
    receiver_task = asyncio.create_task(watch_disconnect(), name="api-sentinel-ws-disconnect-watch")
    tasks = (sender_task, receiver_task)
    try:
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            try:
                task.result()
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        alert_bus.unsubscribe(subscriber)


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
        "persistence_queue_capacity": (
            persistence_worker.queue.maxsize
            if persistence_worker is not None else 0
        ),
        "persistence_queue_max_depth": (
            persistence_worker.max_queue_depth
            if persistence_worker is not None else 0
        ),
        "persistence_queue_wait_count": (
            persistence_worker.queue_wait_count
            if persistence_worker is not None else 0
        ),
        "persistence_queue_wait_avg_ms": (
            persistence_worker.average_queue_wait_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_queue_wait_p95_ms": (
            persistence_worker.p95_queue_wait_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_batch_amortized_per_job_count": (
            persistence_worker.batch_amortized_per_job_duration_count
            if persistence_worker is not None else 0
        ),
        "persistence_batch_amortized_per_job_avg_ms": (
            persistence_worker.average_batch_amortized_per_job_duration_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_batch_amortized_per_job_p95_ms": (
            persistence_worker.p95_batch_amortized_per_job_duration_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_batch_amortized_per_job_max_ms": (
            persistence_worker.max_batch_amortized_per_job_duration_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_store_call_count": (
            persistence_worker.store_call_duration_count
            if persistence_worker is not None else 0
        ),
        "persistence_store_call_avg_ms": (
            persistence_worker.average_store_call_duration_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_store_call_p95_ms": (
            persistence_worker.p95_store_call_duration_ms
            if persistence_worker is not None else 0.0
        ),
        "persistence_store_call_max_ms": (
            persistence_worker.max_store_call_duration_ms
            if persistence_worker is not None else 0.0
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

    receiver = getattr(app.state, "blocklist_verdict_receiver", None)
    receiver_task = getattr(
        app.state, "blocklist_verdict_receiver_task", None
    )
    response["receiver_enabled"] = receiver is not None
    if receiver is None:
        response["receiver_status"] = "disabled"
    else:
        response["receiver_status"] = (
            "running"
            if receiver_task is not None and not receiver_task.done()
            else "stopped"
        )
        response.update(receiver.snapshot())

    producer = getattr(app.state, "blocklist_verdict_producer", None)
    if producer is not None:
        producer_metrics = producer.snapshot()
        response.update({
            "producer_enabled": producer_metrics["producer_enabled"],
            "producer_submitted_count": producer_metrics["submitted_count"],
            "producer_rejected_count": producer_metrics["rejected_count"],
            "producer_disabled_count": producer_metrics["disabled_count"],
            "producer_queue_full_count": producer_metrics["queue_full_count"],
            "producer_submission_queue_depth":
                producer_metrics["submission_queue_depth"],
            "producer_submission_queue_capacity":
                producer_metrics["submission_queue_capacity"],
        })
    else:
        response.update({
            "producer_enabled": False,
            "producer_submitted_count": 0,
            "producer_rejected_count": 0,
            "producer_disabled_count": 0,
            "producer_queue_full_count": 0,
            "producer_submission_queue_depth":
                queues.blocklist_verdict_queue.qsize(),
            "producer_submission_queue_capacity":
                queues.BLOCK_VERDICT_QUEUE_MAX_SIZE,
        })
    policy = getattr(app.state, "blocklist_policy", None)
    response["policy"] = (
        policy.snapshot()
        if policy is not None
        else {
            "enabled": False,
            "allowed_source_count": 0,
            "evaluated_count": 0,
            "submitted_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "last_reason": "not_configured",
        }
    )
    return response

