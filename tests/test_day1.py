
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
    yield
    for queue in (raw_packet_queue, header_queue, metadata_queue):
        while not queue.empty():
            queue.get_nowait()


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
    assert response.json()["day"] == 1


def test_queue_status_endpoint():
    response = client.get("/queue-status")

    assert response.status_code == 200
    assert response.json() == {
        "raw_packet_queue": 0,
        "header_queue": 0,
        "metadata_queue": 0,
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
