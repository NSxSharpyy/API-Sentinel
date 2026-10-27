import asyncio
import json
import sys
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.packet_worker as packet_worker_module
from app import queues
from app.alert_bus import AlertBus
from app.database import Base
from app.ebpf_bridge import read_capture_events
from app.http_pipeline import HTTPMessagePipeline
from app.models import SecurityIncident, TransactionLog
from app.packet_worker import packet_worker
from app.persistence_worker import TransactionPersistenceWorker
from app.queues import QueueWaitMetrics
from app.ring_buffer_consumer import consume_events
from app.transaction_store import TransactionStore


class InMemoryPublisher:
    """Collect publications without opening a ZeroMQ socket."""

    def __init__(self):
        self.messages = []
        self.transactions = []

    def publish(self, message):
        self.messages.append(message)

    def publish_transaction(self, transaction):
        self.transactions.append(transaction)


class OrderedIntegrationStore(TransactionStore):
    """Process login and invoice transactions individually, in order."""

    def can_batch(self, transactions):
        return False


def _http_request(method, path, headers, body=b""):
    headers = dict(headers)
    headers["Content-Length"] = str(len(body))
    headers.setdefault("Connection", "close")

    start_line = f"{method} {path} HTTP/1.1"
    header_lines = [f"{key}: {value}" for key, value in headers.items()]
    return (
        "\r\n".join([start_line, *header_lines]).encode("ascii")
        + b"\r\n\r\n"
        + body
    )


def _http_response(body, status="200 OK"):
    headers = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return headers.encode("ascii") + body


def _make_reader_events():
    """Create reader-contract TCP events for login followed by invoice access."""
    events = []
    packet_number = 0

    def emit(src_port, dst_port, sequence, flags, payload=b""):
        nonlocal packet_number
        packet_number += 1
        events.append({
            "packet_id": f"ebpf-bola-test-{packet_number}",
            "captured_at_ns": time.monotonic_ns(),
            "packet_length": len(payload) + 54,
            "interface_index": 1,
            "source_ip": "127.0.0.1",
            "destination_ip": "127.0.0.1",
            "source_port": src_port,
            "destination_port": dst_port,
            "protocol": 6,
            "sequence_number": sequence,
            "tcp_flags": flags,
            "payload_hex": payload.hex(),
        })

    def exchange(
        client_port,
        server_port,
        client_sequence,
        server_sequence,
        request,
        response,
    ):
        # SYN, SYN-ACK, and client ACK establish each directional stream.
        emit(client_port, server_port, client_sequence, 0x02)
        emit(server_port, client_port, server_sequence, 0x12)
        emit(client_port, server_port, client_sequence + 1, 0x10)

        emit(
            client_port, server_port, client_sequence + 1, 0x18, request
        )
        emit(server_port, client_port, server_sequence + 1, 0x10)
        emit(
            server_port, client_port, server_sequence + 1, 0x18, response
        )

    login_request_body = json.dumps(
        {"username": "alice", "password": "test-password-only-for-this-test"},
        separators=(",", ":"),
    ).encode()

    login_response_body = json.dumps(
        {
            "token": "bola-integration-test-token",
            "user_id": 1,
            "token_type": "Bearer",
        },
        separators=(",", ":"),
    ).encode()

    exchange(
        43001,
        5001,
        10000,
        80000,
        _http_request(
            "POST",
            "/api/v2/auth/login",
            {
                "Host": "127.0.0.1:5001",
                "Content-Type": "application/json",
            },
            login_request_body,
        ),
        _http_response(login_response_body),
    )

    invoice_response_body = json.dumps(
        {"id": 3, "owner_id": 2, "status": "paid"},
        separators=(",", ":"),
    ).encode()

    exchange(
        43002,
        5004,
        20000,
        90000,
        _http_request(
            "GET",
            "/api/v2/billing/invoices/3",
            {
                "Host": "127.0.0.1:5004",
                "Authorization": "Bearer bola-integration-test-token",
            },
        ),
        _http_response(invoice_response_body),
    )

    return events


def test_reader_events_detect_bola_and_redact_sensitive_data(
    monkeypatch, tmp_path
):
    """Replay reader-format packets through processing and in-memory storage."""

    async def run_test():
        assert queues.raw_packet_queue.empty(), (
            "raw_packet_queue is not empty; refusing to mix test traffic"
        )

        # Isolate the queue and global metrics from other tests.
        packet_queue = asyncio.Queue(maxsize=1000)
        monkeypatch.setattr(queues, "raw_packet_queue", packet_queue)
        monkeypatch.setattr(
            packet_worker_module, "raw_packet_queue", packet_queue
        )

        counter_names = (
            "dropped_packet_count",
            "accepted_packet_count",
            "rejected_packet_count",
            "accepted_tcp_event_count",
            "accepted_udp_event_count",
            "tcp_stream_limit_rejection_count",
            "tcp_reassembly_buffer_overflow_count",
            "tcp_packets_processed_count",
            "tcp_syn_packets_count",
            "tcp_payload_packets_count",
            "tcp_payload_bytes_count",
            "tcp_packets_without_stream_count",
            "tcp_payload_delivered_to_http_count",
            "tcp_payload_bytes_delivered_to_http_count",
            "raw_packet_queue_max_depth",
        )
        for name in counter_names:
            monkeypatch.setattr(queues, name, 0)

        monkeypatch.setattr(
            queues, "raw_packet_queue_wait_metrics", QueueWaitMetrics()
        )
        monkeypatch.setattr(queues, "tcp_stream_diagnostics", {}, raising=False)

        capture_path = tmp_path / "synthetic_reader_events.jsonl"
        raw_events = _make_reader_events()
        capture_path.write_text(
            "".join(
                json.dumps(event, separators=(",", ":")) + "\n"
                for event in raw_events
            ),
            encoding="utf-8",
        )

        # This database is in-memory and separate from api_sentinel.db.
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)

        alerts = AlertBus()
        alerts.subscribe()
        store = OrderedIntegrationStore(
            session_factory=sessions,
            alert_bus=alerts,
        )
        persistence = TransactionPersistenceWorker(store)
        publisher = InMemoryPublisher()
        pipeline = HTTPMessagePipeline(
            publisher=publisher,
            persistence_worker=persistence,
        )

        packet_stop = asyncio.Event()
        persistence_stop = asyncio.Event()
        packet_task = asyncio.create_task(
            packet_worker(pipeline, packet_stop)
        )
        persistence_task = asyncio.create_task(
            persistence.run(persistence_stop)
        )

        try:
            # Use the real JSON bridge, not a mocked packet decoder.
            read_command = [
                sys.executable,
                "-c",
                (
                    "import pathlib,sys; "
                    "sys.stdout.write(pathlib.Path(sys.argv[1]).read_text())"
                ),
                str(capture_path),
            ]
            stats = await consume_events(read_capture_events(read_command))

            # Let the TCP worker process every accepted event.
            await asyncio.wait_for(packet_queue.join(), timeout=10)

            # Stop packet processing before draining completed transactions.
            packet_stop.set()
            await asyncio.wait_for(packet_task, timeout=3)

            persistence_stop.set()
            await asyncio.wait_for(persistence_task, timeout=10)

            with sessions() as session:
                records = session.scalars(
                    select(TransactionLog).order_by(TransactionLog.id)
                ).all()
                incidents = session.scalars(
                    select(SecurityIncident)
                ).all()

            rows_by_uri = {row.request_uri: row for row in records}
            login = rows_by_uri.get("/api/v2/auth/login")
            invoice = rows_by_uri.get("/api/v2/billing/invoices/3")

            assert stats.accepted == len(raw_events) == 12
            assert stats.rejected == 0
            assert stats.dropped == 0
            assert len(publisher.messages) == 4
            assert len(pipeline.completed_transactions) == 2
            assert len(publisher.transactions) == 2
            assert persistence.persisted_count == 2
            assert persistence.failed_count == 0
            assert persistence.queue.empty()
            assert login is not None
            assert invoice is not None

            assert len(incidents) == 1
            assert incidents[0].transaction_id == invoice.id
            assert incidents[0].severity == "high"
            assert "Potential BOLA" in incidents[0].title

            detector_metrics = store.bola_detector.snapshot()
            assert detector_metrics["bola_detection_count"] == 1
            assert detector_metrics["capture_to_detection_count"] == 1
            assert alerts.snapshot()["published_count"] == 1

            # Header names are case-insensitive in HTTP.
            authorization = next(
                (
                    value
                    for key, value in (invoice.request_headers or {}).items()
                    if isinstance(key, str)
                    and key.casefold() == "authorization"
                ),
                None,
            )
            assert authorization == "[REDACTED]"
            assert (
                "bola-integration-test-token"
                not in str(invoice.request_headers)
            )

            login_request_body = json.loads(login.request_body)
            login_response_body = json.loads(login.response_body)
            assert login_request_body["password"] == "[REDACTED]"
            assert login_response_body["token"] == "[REDACTED]"

            print("Reader-format events accepted: 12")
            print("Events rejected/dropped: 0/0")
            print("HTTP messages parsed: 4")
            print("Transactions persisted: 2")
            print("High-severity BOLA incidents persisted: 1")
            print("Alerts published: 1")
            print("Persistence failures: 0")
            print("Password, login token, and Authorization redaction: PASS")

        finally:
            packet_stop.set()
            persistence_stop.set()

            for task in (packet_task, persistence_task):
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                packet_task, persistence_task, return_exceptions=True
            )
            engine.dispose()

    asyncio.run(run_test())
