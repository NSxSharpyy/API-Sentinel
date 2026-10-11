
import asyncio
from datetime import datetime, timezone

import pytest

from app.queues import raw_packet_queue
from app.ring_buffer_consumer import consume_events


async def mock_events():
    yield {
        "packet_id": "pkt-day2-001",
        "captured_at": datetime.now(timezone.utc),
        "payload": b"GET /health HTTP/1.1\r\n",
        "source_ip": "10.0.0.10",
        "destination_ip": "10.0.0.20",
        "source_port": 49152,
        "destination_port": 80,
        "protocol": "TCP",
    }

    # Invalid event: packet_id is missing.
    yield {
        "captured_at": datetime.now(timezone.utc),
        "payload": b"invalid packet",
    }


@pytest.fixture(autouse=True)
def clean_packet_queue():
    while not raw_packet_queue.empty():
        raw_packet_queue.get_nowait()

    yield

    while not raw_packet_queue.empty():
        raw_packet_queue.get_nowait()


def test_consumer_accepts_valid_and_rejects_invalid_events():
    async def run_test():
        stats = await consume_events(mock_events())

        assert stats.accepted == 1
        assert stats.rejected == 1
        assert raw_packet_queue.qsize() == 1

        packet = raw_packet_queue.get_nowait()
        assert packet.packet_id == "pkt-day2-001"
        assert packet.destination_port == 80
        assert packet.payload.startswith(b"GET")

    asyncio.run(run_test())


def test_consumer_handles_empty_stream():
    async def empty_events():
        if False:
            yield {}

    async def run_test():
        stats = await consume_events(empty_events())

        assert stats.accepted == 0
        assert stats.rejected == 0
        assert raw_packet_queue.empty()

    asyncio.run(run_test())
