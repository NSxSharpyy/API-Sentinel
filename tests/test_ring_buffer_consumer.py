import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

import app.packet_worker as worker_module
from app import queues
from app.queues import raw_packet_queue
from app.ring_buffer_consumer import consume_events
from app.schemas import RawPacketChunk


async def mock_events():
    """Yield one valid packet event and one invalid event."""
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
    """Ensure the shared packet queue is empty before and after each test."""
    while not raw_packet_queue.empty():
        raw_packet_queue.get_nowait()
        raw_packet_queue.task_done()

    yield

    while not raw_packet_queue.empty():
        raw_packet_queue.get_nowait()
        raw_packet_queue.task_done()


def test_consumer_accepts_valid_and_rejects_invalid_events():
    async def run_test():
        stats = await consume_events(mock_events())

        assert stats.accepted == 1
        assert stats.rejected == 1
        assert stats.dropped == 0
        assert raw_packet_queue.qsize() == 1

        packet = raw_packet_queue.get_nowait()
        raw_packet_queue.task_done()

        assert packet.packet_id == "pkt-day2-001"
        assert isinstance(packet._queue_enqueued_at_ns, int)
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
        assert stats.dropped == 0
        assert raw_packet_queue.empty()

    asyncio.run(run_test())


def test_consumer_counts_packets_dropped_when_queue_is_full():
    async def full_queue_events():
        yield {
            "packet_id": "pkt-full-001",
            "captured_at": datetime.now(timezone.utc),
            "payload": b"GET /health HTTP/1.1\r\n",
            "source_ip": "10.0.0.10",
            "destination_ip": "10.0.0.20",
            "source_port": 49152,
            "destination_port": 80,
            "protocol": "TCP",
        }

    async def run_test():
        original_maxsize = raw_packet_queue._maxsize
        original_dropped_count = queues.dropped_packet_count

        try:
            # Make the queue full without inserting thousands of packets.
            raw_packet_queue._maxsize = 1

            packet = RawPacketChunk.model_validate(
                {
                    "packet_id": "pkt-existing-001",
                    "captured_at": datetime.now(timezone.utc),
                    "payload": b"existing packet",
                    "source_ip": "10.0.0.11",
                    "destination_ip": "10.0.0.20",
                    "source_port": 49153,
                    "destination_port": 80,
                    "protocol": "TCP",
                }
            )
            raw_packet_queue.put_nowait(packet)

            stats = await consume_events(full_queue_events())

            assert stats.accepted == 0
            assert stats.rejected == 0
            assert stats.dropped == 1
            assert queues.dropped_packet_count == original_dropped_count + 1
            assert raw_packet_queue.qsize() == 1
        finally:
            raw_packet_queue._maxsize = original_maxsize
            queues.dropped_packet_count = original_dropped_count

    asyncio.run(run_test())


def test_consumer_to_packet_worker_handoff():
    async def run_test():
        # Use an isolated queue shared by the consumer and worker.
        original_consumer_queue = queues.raw_packet_queue
        original_worker_queue = worker_module.raw_packet_queue

        test_queue = asyncio.Queue(maxsize=10)
        queues.raw_packet_queue = test_queue
        worker_module.raw_packet_queue = test_queue

        pipeline = Mock()
        stop_event = asyncio.Event()

        connection_id = "TCP|10.0.0.10:49152->10.0.0.20:80"

        async def events():
            # TCP handshake: SYN establishes the initial sequence.
            yield {
                "packet_id": "pkt-syn-001",
                "captured_at": datetime.now(timezone.utc),
                "payload": b"",
                "source_ip": "10.0.0.10",
                "destination_ip": "10.0.0.20",
                "source_port": 49152,
                "destination_port": 80,
                "protocol": "TCP",
                "sequence_number": 99,
                "tcp_flags": ["SYN"],
            }

            # The following payload begins at sequence number 100.
            yield {
                "packet_id": "pkt-data-001",
                "captured_at": datetime.now(timezone.utc),
                "payload": (
                    b"GET /health HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"\r\n"
                ),
                "source_ip": "10.0.0.10",
                "destination_ip": "10.0.0.20",
                "source_port": 49152,
                "destination_port": 80,
                "protocol": "TCP",
                "sequence_number": 100,
                "tcp_flags": [],
            }

        worker_task = None

        try:
            # Consumer validates and enqueues both events.
            stats = await consume_events(events())

            assert stats.accepted == 2
            assert stats.rejected == 0
            assert stats.dropped == 0
            assert test_queue.qsize() == 2

            # Worker consumes those same queued events.
            worker_task = asyncio.create_task(
                worker_module.packet_worker(pipeline, stop_event)
            )

            await asyncio.wait_for(test_queue.join(), timeout=2)

            # The SYN and data payload should produce one HTTP pipeline call.
            pipeline.feed.assert_called_once_with(
                b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n",
                connection_id=connection_id,
            )
        finally:
            stop_event.set()

            try:
                if worker_task is not None:
                    await asyncio.wait_for(worker_task, timeout=2)
            finally:
                queues.raw_packet_queue = original_consumer_queue
                worker_module.raw_packet_queue = original_worker_queue