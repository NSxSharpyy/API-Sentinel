import tracemalloc
import asyncio
import logging
import os
import time
from pathlib import Path
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import queues
from app.capture_supervisor import supervise_capture
from app.alert_bus import AlertBus
from app.api_v1 import router as api_v1_router
from app.config import settings
from app.blocklist_verdicts import BlocklistVerdictProducer
from app.http_pipeline import HTTPMessagePipeline
from app.message_broker import HTTPTransactionPublisher
from app.transaction_websocket import TransactionWebSocketStream
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
from app.memory_profiler import MemoryProfiler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistence and optional packet capture services."""
    capture_enabled_raw = os.getenv(
        "API_SENTINEL_CAPTURE_ENABLED", "1"
    ).strip().lower()

    if capture_enabled_raw not in {
        "1", "true", "yes", "on",
        "0", "false", "no", "off",
    }:
        raise ValueError(
            "API_SENTINEL_CAPTURE_ENABLED must be a boolean value"
        )

    capture_enabled = capture_enabled_raw in {
        "1", "true", "yes", "on"
    }

    # Optional Python allocation tracing for Day 28 memory profiling.
    # It is disabled by default because tracing adds runtime overhead.
    memory_profile_enabled = os.getenv(
        "API_SENTINEL_MEMORY_PROFILE_ENABLED", "0"
    ).strip().lower() in {"1", "true", "yes"}

    tracemalloc_enabled = (
        os.getenv("API_SENTINEL_TRACEMALLOC_ENABLED", "0")
        .strip()
        .lower() in {"1", "true", "yes"}
    ) or memory_profile_enabled

    app.state.memory_profile_enabled = memory_profile_enabled
    app.state.tracemalloc_enabled = False

    if tracemalloc_enabled:
        try:
            tracemalloc_frames = int(
                os.getenv("API_SENTINEL_TRACEMALLOC_FRAMES", "10")
            )
        except ValueError as exc:
            raise ValueError(
                "API_SENTINEL_TRACEMALLOC_FRAMES must be an integer"
            ) from exc

        if not 1 <= tracemalloc_frames <= 25:
            raise ValueError(
                "API_SENTINEL_TRACEMALLOC_FRAMES must be between 1 and 25"
            )

        if not tracemalloc.is_tracing():
            tracemalloc.start(tracemalloc_frames)

        app.state.tracemalloc_enabled = tracemalloc.is_tracing()
        logger.info(
            "Python memory tracing enabled: frames=%d",
            tracemalloc_frames,
        )

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
    capture_stop_event = asyncio.Event()
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
    transaction_stream = TransactionWebSocketStream()

    # Keep kernel synchronization opt-in.
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

            blocklist_receiver = BlocklistVerdictReceiver(
                blocklist_producer,
                endpoint=verdict_endpoint,
            )

            if blocklist_policy_requested:
                raw_allowlist = os.getenv(
                    "API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS", ""
                )

                allowed_source_ips = [
                    item.strip()
                    for item in raw_allowlist.split(",")
                    if item.strip()
                ]

                if not allowed_source_ips:
                    raise ValueError(
                        "Blocklist policy requires an exact allowlist in "
                        "API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS"
                    )

                from app.blocklist_policy import (
                    BlocklistPolicy,
                    ThreadOwnedVerdictSender,
                )
                from app.blocklist_verdict_client import BlocklistVerdictSender

                blocklist_sender = ThreadOwnedVerdictSender(
                    lambda: BlocklistVerdictSender(
                        endpoint=blocklist_receiver.endpoint
                    )
                )

                blocklist_policy = BlocklistPolicy(
                    blocklist_sender,
                    allowed_source_ips,
                    enabled=True,
                    ttl_seconds=int(
                        os.getenv(
                            "API_SENTINEL_BLOCKLIST_VERDICT_TTL_SECONDS",
                            "60",
                        )
                    ),
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
    app.state.capture_stop_event = capture_stop_event
    app.state.http_pipeline = pipeline
    app.state.http_publisher = publisher
    app.state.transaction_stream = transaction_stream
    app.state.transaction_store = transaction_store
    app.state.alert_bus = alert_bus
    app.state.persistence_worker = persistence_worker
    app.state.memory_profiler = None
    app.state.capture_enabled = capture_enabled
    app.state.capture_status = (
        "starting" if capture_enabled else "disabled"
    )
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

    capture_task = None

    if capture_enabled:
        # This reader requires the intended Linux/WSL eBPF environment.
        reader_command = [
            "sudo",
            "-n",
            "/usr/local/sbin/api-sentinel-ring-reader-day16",
            "/sys/fs/bpf/api_sentinel_day16_events",
        ]

        capture_task = asyncio.create_task(
            supervise_capture(
                reader_command,
                capture_stop_event,
                on_status=update_capture_status,
            ),
            name="api-sentinel-capture-supervisor",
        )
        logger.info("API-Sentinel eBPF capture supervisor started")
    else:
        logger.info(
            "API-Sentinel eBPF capture disabled by configuration"
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

    transaction_stream.start(asyncio.get_running_loop())
    memory_profiler = None

    try:
        if memory_profile_enabled:
            sample_interval = float(os.getenv(
                "API_SENTINEL_MEMORY_PROFILE_INTERVAL_SECONDS", "60"
            ))
            drain_timeout = float(os.getenv(
                "API_SENTINEL_MEMORY_PROFILE_DRAIN_TIMEOUT_SECONDS", "120"
            ))
            quiet_period = float(os.getenv(
                "API_SENTINEL_MEMORY_PROFILE_QUIET_PERIOD_SECONDS", "2"
            ))
            output_dir = Path(os.getenv(
                "API_SENTINEL_MEMORY_PROFILE_OUTPUT_DIR", "artifacts/day28"
            )).expanduser()
            output_path = output_dir / (
                f"memory-profile-{time.time_ns()}-{os.getpid()}.jsonl"
            )

            def memory_snapshot_provider():
                snapshot = _runtime_memory_snapshot()
                tcp_diagnostics = getattr(
                    queues, "tcp_stream_diagnostics", {}
                )
                capture_task = getattr(app.state, "capture_task", None)
                packet_task = getattr(app.state, "packet_worker_task", None)
                persistence_task = getattr(
                    app.state, "persistence_worker_task", None
                )
                capture_status = getattr(
                    app.state, "capture_status", "unknown"
                )

                return {
                    **snapshot,
                    "capture_enabled": capture_enabled,
                    "capture_status": capture_status,
                    "capture_running": (
                        capture_status == "running"
                        and capture_task is not None
                        and not capture_task.done()
                    ),
                    "capture_supervisor_running": (
                        capture_task is not None and not capture_task.done()
                    ),
                    "packet_worker_running": (
                        packet_task is not None and not packet_task.done()
                    ),
                    "persistence_worker_running": (
                        persistence_task is not None
                        and not persistence_task.done()
                    ),
                    "raw_packet_queue_depth": raw_packet_queue.qsize(),
                    "persistence_queue_depth": persistence_worker.queue.qsize(),
                    "accepted_packet_count": queues.accepted_packet_count,
                    "rejected_packet_count": queues.rejected_packet_count,
                    "dropped_packet_count": queues.dropped_packet_count,
                    "accepted_tcp_event_count": queues.accepted_tcp_event_count,
                    "accepted_udp_event_count": queues.accepted_udp_event_count,
                    "tcp_packets_processed_count":
                        queues.tcp_packets_processed_count,
                    "tcp_payload_delivered_to_http_count":
                        queues.tcp_payload_delivered_to_http_count,
                    "tcp_stream_limit_rejection_count":
                        queues.tcp_stream_limit_rejection_count,
                    "tcp_half_closed_connection_limit_rejection_count":
                        queues.tcp_half_closed_connection_limit_rejection_count,
                    "tcp_reassembly_buffer_overflow_count":
                        queues.tcp_reassembly_buffer_overflow_count,
                    "transaction_processing_count":
                        pipeline.transaction_processing_count,
                    "persisted_transaction_count":
                        persistence_worker.persisted_count,
                    "persistence_failed_count":
                        persistence_worker.failed_count,
                    "persistence_rejected_count":
                        persistence_worker.rejected_count,
                    "http_open_connection_count": pipeline.open_connections,
                    "http_pending_request_count":
                        pipeline.correlator.pending_request_count,
                    "active_tcp_stream_count":
                        tcp_diagnostics.get("active_streams", 0),
                }

            def memory_activity_provider():
                return (
                    queues.accepted_packet_count,
                    queues.rejected_packet_count,
                    queues.dropped_packet_count,
                    queues.tcp_packets_processed_count,
                    pipeline.transaction_processing_count,
                    persistence_worker.persisted_count,
                    persistence_worker.failed_count,
                    persistence_worker.rejected_count,
                )

            memory_profiler = MemoryProfiler(
                output_path=output_path,
                snapshot_provider=memory_snapshot_provider,
                activity_provider=memory_activity_provider,
                raw_packet_queue=raw_packet_queue,
                persistence_queue=persistence_worker.queue,
                packet_worker_task=worker_task,
                persistence_worker_task=persistence_task,
                sample_interval_seconds=sample_interval,
                drain_timeout_seconds=drain_timeout,
                quiet_period_seconds=quiet_period,
            )
            app.state.memory_profiler = memory_profiler
            app.state.memory_profile_output_path = str(output_path)

            await memory_profiler.start()
            logger.info(
                "Day 28 memory profiler started: output=%s interval=%ss",
                output_path,
                sample_interval,
            )

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
                logger.exception(
                    "Day 19 drop-audit worker failed during shutdown"
                )

        # Stop capture first when it was enabled. Keep the packet worker
        # alive until the reader has terminated and cannot enqueue packets.
        if capture_task is not None:
            capture_stop_event.set()
            capture_task.cancel()

            try:
                await capture_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "Capture supervisor failed during shutdown"
                )

        # Capture is fully stopped. Drain both processing queues while
        # their workers are still alive.
        if memory_profiler is not None:
            try:
                await memory_profiler.drain()
                logger.info("Day 28 packet and persistence queues drained")
            except Exception:
                logger.exception(
                    "Day 28 memory profiler could not confirm a clean queue drain"
                )

        # Now tell the packet worker to finish and exit.
        stop_event.set()

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
            logger.exception("Packet worker failed during shutdown")

        # Stop transaction delivery after packet processing has stopped.
        await asyncio.to_thread(transaction_stream.stop)

        # Drain persistence before stopping alert delivery.
        persistence_stop_event.set()

        try:
            await persistence_task
        except asyncio.CancelledError:
            logger.warning("Persistence worker was cancelled")
        except Exception:
            logger.exception("Persistence worker failed during shutdown")
        finally:
            if memory_profiler is not None:
                try:
                    memory_profiler.snapshot("post_shutdown")
                except Exception:
                    logger.exception(
                        "Could not write Day 28 post-shutdown snapshot"
                    )

                try:
                    await memory_profiler.stop()
                except Exception:
                    logger.exception("Could not close Day 28 memory profiler")

            alert_bus.close()
            publisher.close()

        # Allow submitted verdicts time to reach the receiver.
        if blocklist_policy is not None and blocklist_receiver is not None:
            expected = blocklist_policy.snapshot()["submitted_count"]
            deadline = asyncio.get_running_loop().time() + 2.0

            while (
                blocklist_receiver.snapshot()["receiver_messages_accepted"]
                < expected
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.02)

            accepted = blocklist_receiver.snapshot()[
                "receiver_messages_accepted"
            ]

            if accepted < expected:
                logger.warning(
                    "Timed out waiting for accepted verdicts: "
                    "expected at least %d, accepted %d",
                    expected,
                    accepted,
                )

        # Stop verdict intake after persistence has completed.
        if blocklist_receiver_task is not None:
            blocklist_receiver_stop_event.set()

            try:
                await asyncio.wait_for(
                    blocklist_receiver_task,
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                blocklist_receiver_task.cancel()

                try:
                    await blocklist_receiver_task
                except asyncio.CancelledError:
                    pass

            except asyncio.CancelledError:
                pass

            except Exception:
                logger.exception(
                    "Blocklist verdict receiver failed during shutdown"
                )

            finally:
                if blocklist_receiver is not None:
                    blocklist_receiver.close()

        # Stop synchronization after receiver intake has completed.
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
                logger.exception(
                    "Blocklist worker failed during shutdown"
                )

            finally:
                if blocklist_writer is not None:
                    try:
                        blocklist_writer.close()
                    except Exception:
                        logger.exception(
                            "Failed to close blocklist map writer"
                        )

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

# CORS: allow the local React/Vite development server to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.websocket("/ws/transactions")
async def websocket_transactions(websocket: WebSocket):
    """Stream completed HTTP transaction metadata to dashboard clients."""
    transaction_stream = getattr(
        websocket.app.state,
        "transaction_stream",
        None,
    )

    if transaction_stream is None:
        await websocket.close(
            code=1013,
            reason="Transaction stream is not initialized",
        )
        return

    client_queue = transaction_stream.subscribe()
    await websocket.accept()

    async def stream_transactions():
        while True:
            event = await client_queue.get()
            await websocket.send_json(event)

    async def watch_disconnect():
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                return

    sender_task = asyncio.create_task(
        stream_transactions(),
        name="api-sentinel-ws-transaction-sender",
    )
    receiver_task = asyncio.create_task(
        watch_disconnect(),
        name="api-sentinel-ws-transaction-disconnect-watch",
    )

    tasks = (sender_task, receiver_task)

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
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
        transaction_stream.unsubscribe(client_queue)


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """Stream committed security alerts to connected frontend clients.

    Alert delivery is best-effort and process-local. Expose this endpoint
    only on a trusted development network until authentication and
    authorization are implemented.
    """
    alert_bus = getattr(websocket.app.state, "alert_bus", None)

    if alert_bus is None:
        await websocket.close(
            code=1013,
            reason="Alert bus is not initialized",
        )
        return

    try:
        subscriber = alert_bus.subscribe()
    except RuntimeError:
        await websocket.close(
            code=1013,
            reason="Alert bus is shutting down",
        )
        return

    await websocket.accept()

    async def stream_alerts():
        while True:
            try:
                event = subscriber.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.025)
                continue

            await websocket.send_json(event.to_dict())

    async def watch_disconnect():
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                return

    sender_task = asyncio.create_task(
        stream_alerts(),
        name="api-sentinel-ws-alert-sender",
    )
    receiver_task = asyncio.create_task(
        watch_disconnect(),
        name="api-sentinel-ws-disconnect-watch",
    )

    tasks = (sender_task, receiver_task)

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
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


def _runtime_memory_snapshot():
    """Read process RSS and host-memory utilization on Linux."""
    process_rss_bytes = None
    system_total_bytes = None
    system_available_bytes = None

    try:
        with open("/proc/self/status", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("VmRSS:"):
                    process_rss_bytes = int(line.split()[1]) * 1024
                    break
    except (OSError, ValueError, IndexError):
        pass

    try:
        with open("/proc/meminfo", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("MemTotal:"):
                    system_total_bytes = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    system_available_bytes = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass

    used_percent = None

    if (
        system_total_bytes is not None
        and system_total_bytes > 0
        and system_available_bytes is not None
    ):
        used_percent = round(
            100
            * (system_total_bytes - system_available_bytes)
            / system_total_bytes,
            2,
        )

    tracing_enabled = tracemalloc.is_tracing()
    traced_current_bytes = None
    traced_peak_bytes = None
    tracemalloc_overhead_bytes = None

    if tracing_enabled:
        traced_current_bytes, traced_peak_bytes = (
            tracemalloc.get_traced_memory()
        )
        tracemalloc_overhead_bytes = tracemalloc.get_tracemalloc_memory()

    return {
        "process_rss_bytes": process_rss_bytes,
        "system_total_bytes": system_total_bytes,
        "system_available_bytes": system_available_bytes,
        "system_used_percent": used_percent,
        "tracemalloc_enabled": tracing_enabled,
        "traced_current_bytes": traced_current_bytes,
        "traced_peak_bytes": traced_peak_bytes,
        "tracemalloc_overhead_bytes": tracemalloc_overhead_bytes,
    }


def _queue_health_snapshot():
    persistence_worker = getattr(app.state, "persistence_worker", None)

    persistence_queue = (
        getattr(persistence_worker, "queue", None)
        if persistence_worker is not None
        else None
    )

    queues_by_name = {
        "raw_packet": raw_packet_queue,
        "header": header_queue,
        "metadata": metadata_queue,
        "persistence": persistence_queue,
    }

    result = {}

    for name, current_queue in queues_by_name.items():
        result[name] = {
            "depth": (
                current_queue.qsize()
                if current_queue is not None
                else None
            ),
            "capacity": (
                current_queue.maxsize
                if current_queue is not None
                else None
            ),
        }

    return result


@app.get("/healthz")
async def healthz():
    """Liveness probe: the API process can answer HTTP requests."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness probe: report required workers and runtime resources."""
    capture_enabled = getattr(app.state, "capture_enabled", True)
    capture_status = getattr(app.state, "capture_status", "stopped")
    capture_task = getattr(app.state, "capture_task", None)

    capture_running = (
        capture_status == "running"
        and capture_task is not None
        and not capture_task.done()
    )

    # Capture is optional in API-only deployments. When enabled, it must
    # actually be running; when disabled, it is not a readiness blocker.
    capture_ready = not capture_enabled or capture_running

    persistence_worker = getattr(app.state, "persistence_worker", None)
    persistence_task = getattr(
        app.state,
        "persistence_worker_task",
        None,
    )

    persistence_running = (
        persistence_worker is not None
        and persistence_task is not None
        and not persistence_task.done()
    )

    pipeline_initialized = (
        getattr(app.state, "http_pipeline", None) is not None
    )

    checks = {
        "capture_ready": capture_ready,
        "persistence_worker_running": persistence_running,
        "http_pipeline_initialized": pipeline_initialized,
    }

    ready = all(checks.values())

    payload = {
        "status": "ready" if ready else "not_ready",
        "capture": {
            "enabled": capture_enabled,
            "running": capture_running,
            "status": capture_status,
        },
        "checks": checks,
        "memory": _runtime_memory_snapshot(),
        "queue_depths": _queue_health_snapshot(),
    }

    return JSONResponse(
        status_code=200 if ready else 503,
        content=payload,
    )


@app.get("/queue-status")
async def queue_status():
    capture_task = getattr(app.state, "capture_task", None)
    capture_status = getattr(app.state, "capture_status", "stopped")

    persistence_worker = getattr(
        app.state,
        "persistence_worker",
        None,
    )

    persistence_store = getattr(
        persistence_worker,
        "store",
        None,
    )

    persistence_task = getattr(
        app.state,
        "persistence_worker_task",
        None,
    )

    pipeline = getattr(app.state, "http_pipeline", None)

    return {
        "raw_packet_queue": raw_packet_queue.qsize(),
        "header_queue": header_queue.qsize(),
        "metadata_queue": metadata_queue.qsize(),

        "persistence_queue_size": (
            persistence_worker.queue.qsize()
            if persistence_worker is not None else 0
        ),
        "persistence_persisted_count": (
            persistence_worker.persisted_count
            if persistence_worker is not None else 0
        ),
        "persistence_failed_count": (
            persistence_worker.failed_count
            if persistence_worker is not None else 0
        ),
        "persistence_rejected_count": (
            persistence_worker.rejected_count
            if persistence_worker is not None else 0
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

        "persistence_batch_attempt_count": (
            persistence_worker.batch_attempt_count
            if persistence_worker is not None else 0
        ),
        "persistence_batch_attempted_job_count": (
            persistence_worker.batch_attempted_job_count
            if persistence_worker is not None else 0
        ),
        "persistence_batch_success_count": (
            persistence_worker.batch_success_count
            if persistence_worker is not None else 0
        ),
        "persistence_batch_successful_job_count": (
            persistence_worker.batch_successful_job_count
            if persistence_worker is not None else 0
        ),
        "persistence_batch_failure_count": (
            persistence_worker.batch_failure_count
            if persistence_worker is not None else 0
        ),
        "persistence_batch_size_avg": (
            persistence_worker.average_batch_size
            if persistence_worker is not None else 0.0
        ),
        "persistence_batch_size_p95": (
            persistence_worker.p95_batch_size
            if persistence_worker is not None else 0.0
        ),
        "persistence_batch_size_max": (
            persistence_worker.max_observed_batch_size
            if persistence_worker is not None else 0
        ),
        "persistence_batch_size_sample_count": (
            persistence_worker.batch_size_sample_count
            if persistence_worker is not None else 0
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

        "persistence_store_batch_preparation_count": getattr(
            persistence_store,
            "batch_preparation_duration_count",
            0,
        ),
        "persistence_store_batch_preparation_avg_ms": getattr(
            persistence_store,
            "average_batch_preparation_duration_ms",
            0.0,
        ),
        "persistence_store_batch_preparation_p95_ms": getattr(
            persistence_store,
            "p95_batch_preparation_duration_ms",
            0.0,
        ),
        "persistence_store_batch_preparation_max_ms": getattr(
            persistence_store,
            "max_batch_preparation_duration_ms",
            0.0,
        ),

        "persistence_store_batch_insert_count": getattr(
            persistence_store,
            "batch_insert_duration_count",
            0,
        ),
        "persistence_store_batch_insert_avg_ms": getattr(
            persistence_store,
            "average_batch_insert_duration_ms",
            0.0,
        ),
        "persistence_store_batch_insert_p95_ms": getattr(
            persistence_store,
            "p95_batch_insert_duration_ms",
            0.0,
        ),
        "persistence_store_batch_insert_max_ms": getattr(
            persistence_store,
            "max_batch_insert_duration_ms",
            0.0,
        ),

        "persistence_store_batch_commit_count": getattr(
            persistence_store,
            "batch_commit_duration_count",
            0,
        ),
        "persistence_store_batch_commit_avg_ms": getattr(
            persistence_store,
            "average_batch_commit_duration_ms",
            0.0,
        ),
        "persistence_store_batch_commit_p95_ms": getattr(
            persistence_store,
            "p95_batch_commit_duration_ms",
            0.0,
        ),
        "persistence_store_batch_commit_max_ms": getattr(
            persistence_store,
            "max_batch_commit_duration_ms",
            0.0,
        ),

        "http_completed_transaction_count": (
            len(pipeline.completed_transactions)
            if pipeline is not None else 0
        ),
        "http_completed_transaction_history_size": (
            len(pipeline.completed_transactions)
            if pipeline is not None else 0
        ),
        "http_completed_transaction_history_capacity": (
            pipeline.completed_transactions.maxlen
            if pipeline is not None else 0
        ),
        "http_parsed_request_count": (
            pipeline.parsed_request_count
            if pipeline is not None else 0
        ),
        "http_parsed_response_count": (
            pipeline.parsed_response_count
            if pipeline is not None else 0
        ),
        "http_dropped_request_count": (
            pipeline.correlator.dropped_requests
            if pipeline is not None else 0
        ),
        "http_expired_request_count": (
            pipeline.correlator.expired_requests
            if pipeline is not None else 0
        ),
        "http_capacity_evicted_request_count": (
            pipeline.correlator.capacity_evicted_requests
            if pipeline is not None else 0
        ),
        "http_connection_closed_request_count": (
            pipeline.correlator.connection_closed_requests
            if pipeline is not None else 0
        ),
        "http_pending_request_count": (
            pipeline.correlator.pending_request_count
            if pipeline is not None else 0
        ),
        "http_unmatched_response_count": (
            pipeline.correlator.unmatched_responses
            if pipeline is not None else 0
        ),
        "transaction_processing_count": (
            pipeline.transaction_processing_count
            if pipeline is not None else 0
        ),
        "last_transaction_processing_latency_ms": (
            pipeline.last_transaction_processing_latency_ms
            if pipeline is not None else 0.0
        ),
        "average_transaction_processing_latency_ms": (
            pipeline.average_transaction_processing_latency_ms
            if pipeline is not None else 0.0
        ),
        "max_transaction_processing_latency_ms": (
            pipeline.max_transaction_processing_latency_ms
            if pipeline is not None else 0.0
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
            if pipeline is not None else 0
        ),
        "http_unmatched_response_count": (
            pipeline.correlator.unmatched_responses
            if pipeline is not None else 0
        ),
        "http_open_connection_count": (
            pipeline.open_connections
            if pipeline is not None else 0
        ),

        "accepted_packet_count": queues.accepted_packet_count,
        "accepted_tcp_event_count": queues.accepted_tcp_event_count,
        "accepted_udp_event_count": queues.accepted_udp_event_count,
        "rejected_packet_count": queues.rejected_packet_count,
        "dropped_packet_count": queues.dropped_packet_count,
        "tcp_stream_limit_rejection_count": (
            queues.tcp_stream_limit_rejection_count
        ),
        "tcp_half_closed_connection_limit_rejection_count": (
            queues.tcp_half_closed_connection_limit_rejection_count
        ),
        "tcp_reassembly_buffer_overflow_count": (
            queues.tcp_reassembly_buffer_overflow_count
        ),
        "tcp_packets_processed_count": queues.tcp_packets_processed_count,
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

    parsers = tuple(pipeline._parsers.values())
    stream_diagnostics = getattr(queues, "tcp_stream_diagnostics", {})
    if not isinstance(stream_diagnostics, dict):
        stream_diagnostics = {}

    return {
        "parser_count": len(parsers),
        "buffered_parser_count": sum(bool(parser.buffer) for parser in parsers),
        "total_buffered_bytes": sum(len(parser.buffer) for parser in parsers),
        "pending_head_responses": sum(
            parser.pending_head_responses for parser in parsers
        ),
        "parsed_request_count": pipeline.parsed_request_count,
        "parsed_response_count": pipeline.parsed_response_count,
        "transaction_processing_count": pipeline.transaction_processing_count,
        "completed_transactions": len(pipeline.completed_transactions),
        "completed_transaction_history_size": len(
            pipeline.completed_transactions
        ),
        "completed_transaction_history_capacity": (
            pipeline.completed_transactions.maxlen
        ),
        "pending_requests": pipeline.correlator.pending_request_count,
        "unmatched_responses": pipeline.correlator.unmatched_responses,
        "dropped_requests": pipeline.correlator.dropped_requests,
        "expired_requests": pipeline.correlator.expired_requests,
        "capacity_evicted_requests": (
            pipeline.correlator.capacity_evicted_requests
        ),
        "connection_closed_requests": (
            pipeline.correlator.connection_closed_requests
        ),
        "drop_reason_counts": dict(
            pipeline.correlator.drop_reason_counts
        ),
        "drop_sample_capacity": (
            pipeline.correlator.recent_drop_samples.maxlen
        ),
        "active_tcp_streams": stream_diagnostics.get("active_streams", 0),
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
        app.state,
        "blocklist_verdict_receiver_task",
        None,
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
