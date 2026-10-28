from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.queues import (
    header_queue,
    metadata_queue,
    raw_packet_queue,
)
from app.schemas import HeaderData, PacketMetadata, RawPacketChunk


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_queues():
    """Keep tests independent by clearing shared in-memory queues."""
    for queue in (raw_packet_queue, header_queue, metadata_queue):
        while not queue.empty():
            queue.get_nowait()
            queue.task_done()
    yield
    for queue in (raw_packet_queue, header_queue, metadata_queue):
        while not queue.empty():
            queue.get_nowait()
            queue.task_done()


def test_raw_packet_schema():
    packet = RawPacketChunk(
        packet_id="pkt-001",
        captured_at=datetime.now(timezone.utc),
        payload=b"GET / HTTP/1.1\r\n",
        source_ip="10.0.0.10",
        destination_ip="10.0.0.20",
        source_port=49152,
        destination_port=80,
        protocol="TCP",
        sequence_number=1000,
    )

    assert packet.packet_id == "pkt-001"
    assert packet.payload.startswith(b"GET")
    assert packet.destination_port == 80


def test_header_schema():
    header = HeaderData(name="Host", value="lab.local")

    assert header.name == "Host"
    assert header.value == "lab.local"


def test_metadata_schema():
    metadata = PacketMetadata(
        packet_id="pkt-001",
        captured_at=datetime.now(timezone.utc),
        interface="Ethernet",
        direction="ingress",
        tcp_flags=["ACK", "PSH"],
    )

    assert metadata.interface == "Ethernet"
    assert "ACK" in metadata.tcp_flags


def test_invalid_port_is_rejected():
    with pytest.raises(ValidationError):
        RawPacketChunk(
            packet_id="pkt-invalid",
            captured_at=datetime.now(timezone.utc),
            payload=b"test",
            source_port=99999,
        )


def test_missing_packet_id_is_rejected():
    with pytest.raises(ValidationError):
        RawPacketChunk(
            captured_at=datetime.now(timezone.utc),
            payload=b"test",
        )


def test_async_queues():
    packet = RawPacketChunk(
        packet_id="pkt-queue-001",
        captured_at=datetime.now(timezone.utc),
        payload=b"test payload",
    )
    header = HeaderData(name="Content-Type", value="application/json")
    metadata = PacketMetadata(
        packet_id="pkt-queue-001",
        captured_at=datetime.now(timezone.utc),
    )

    raw_packet_queue.put_nowait(packet)
    header_queue.put_nowait(header)
    metadata_queue.put_nowait(metadata)

    assert raw_packet_queue.get_nowait().packet_id == "pkt-queue-001"
    assert header_queue.get_nowait().name == "Content-Type"
    assert metadata_queue.get_nowait().packet_id == "pkt-queue-001"


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert "day" not in response.json()



def test_queue_status_endpoint():
    response = client.get("/queue-status")

    assert response.status_code == 200
    assert response.json() == {
        "raw_packet_queue": 0,
        "header_queue": 0,
        "metadata_queue": 0,
        "persistence_queue_size": 0,
        "persistence_persisted_count": 0,
        "persistence_failed_count": 0,
        "persistence_rejected_count": 0,
        "persistence_worker_running": False,
        "persistence_queue_capacity": 0,
        "persistence_queue_max_depth": 0,
        "persistence_queue_wait_count": 0,
        "persistence_queue_wait_avg_ms": 0.0,
        "persistence_queue_wait_p95_ms": 0.0,
        "persistence_batch_amortized_per_job_count": 0,
        "persistence_batch_amortized_per_job_avg_ms": 0.0,
        "persistence_batch_amortized_per_job_p95_ms": 0.0,
        "persistence_batch_amortized_per_job_max_ms": 0.0,
        "persistence_batch_attempt_count": 0,
        "persistence_batch_attempted_job_count": 0,
        "persistence_batch_success_count": 0,
        "persistence_batch_successful_job_count": 0,
        "persistence_batch_failure_count": 0,
        "persistence_batch_size_avg": 0.0,
        "persistence_batch_size_p95": 0.0,
        "persistence_batch_size_max": 0,
        "persistence_batch_size_sample_count": 0,
        "persistence_store_call_count": 0,
        "persistence_store_call_avg_ms": 0.0,
        "persistence_store_call_p95_ms": 0.0,
        "persistence_store_call_max_ms": 0.0,
        "persistence_store_batch_preparation_count": 0,
        "persistence_store_batch_preparation_avg_ms": 0.0,
        "persistence_store_batch_preparation_p95_ms": 0.0,
        "persistence_store_batch_preparation_max_ms": 0.0,
        "persistence_store_batch_commit_count": 0,
        "persistence_store_batch_commit_avg_ms": 0.0,
        "persistence_store_batch_commit_p95_ms": 0.0,
        "persistence_store_batch_commit_max_ms": 0.0,
        "http_completed_transaction_count": 0,
"transaction_processing_count": 0,
"last_transaction_processing_latency_ms": 0.0,
"average_transaction_processing_latency_ms": 0.0,
"max_transaction_processing_latency_ms": 0.0,
        "capture_to_publish_count": 0,
        "last_capture_to_publish_latency_ms": 0.0,
        "average_capture_to_publish_latency_ms": 0.0,
        "max_capture_to_publish_latency_ms": 0.0,
        "http_pending_request_count": 0,
        "http_unmatched_response_count": 0,
        "http_open_connection_count": 0,
        "accepted_packet_count": 0,
        "accepted_tcp_event_count": 0,
        "accepted_udp_event_count": 0,
        "rejected_packet_count": 0,
        "dropped_packet_count": 0,
        "tcp_stream_limit_rejection_count": 0,
        "tcp_reassembly_buffer_overflow_count": 0,
        "tcp_packets_processed_count": 0,
        "tcp_syn_packets_count": 0,
        "tcp_payload_packets_count": 0,
        "tcp_payload_bytes_count": 0,
        "tcp_packets_without_stream_count": 0,
        "tcp_payload_delivered_to_http_count": 0,
        "tcp_payload_bytes_delivered_to_http_count": 0,
        "capture_running": False,
    }

def test_unknown_endpoint_returns_404():
    response = client.get("/does-not-exist")

    assert response.status_code == 404


def test_queue_burst():
    for i in range(1000):
        raw_packet_queue.put_nowait(
            RawPacketChunk(
                packet_id=f"burst-{i}",
                captured_at=datetime.now(timezone.utc),
                payload=b"test",
                protocol="TCP",
            )
        )

    assert raw_packet_queue.qsize() == 1000
