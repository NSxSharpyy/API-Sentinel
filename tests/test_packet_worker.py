import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

import app.packet_worker as worker_module
from app.http_reassembly import HTTPParseError
from app.packet_worker import build_connection_id
from app.schemas import RawPacketChunk


@pytest.fixture
def packet_queue(monkeypatch):
    """Provide an isolated queue for each test."""
    queue = asyncio.Queue(maxsize=100)
    monkeypatch.setattr(worker_module, "raw_packet_queue", queue)
    return queue


def make_packet(**overrides) -> RawPacketChunk:
    """Create a valid packet for worker tests."""
    data = {
        "packet_id": "pkt-worker-001",
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
    data.update(overrides)
    return RawPacketChunk(**data)


def start_worker(queue, pipeline):
    """Start a worker and return its task and stop event."""
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        worker_module.packet_worker(pipeline, stop_event)
    )
    return task, stop_event


async def stop_worker(task, stop_event):
    stop_event.set()
    await asyncio.wait_for(task, timeout=2)


def test_build_connection_id_is_directional():
    outgoing = make_packet()
    incoming = make_packet(
        source_ip="10.0.0.20",
        destination_ip="10.0.0.10",
        source_port=80,
        destination_port=49152,
    )

    assert build_connection_id(outgoing) != build_connection_id(incoming)


def test_build_connection_id_returns_none_without_tuple():
    packet = make_packet(source_ip=None)

    assert build_connection_id(packet) is None


def test_worker_reassembles_payload_after_syn(packet_queue):
    async def run_test():
        pipeline = Mock()
        syn = make_packet(
            packet_id="syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        data = make_packet(sequence_number=100)

        await packet_queue.put(syn)
        await packet_queue.put(data)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            pipeline.feed.assert_called_once_with(
                data.payload,
                connection_id=build_connection_id(data),
            )
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_buffers_out_of_order_payload(packet_queue):
    async def run_test():
        pipeline = Mock()
        connection_id = build_connection_id(make_packet())

        syn = make_packet(
            packet_id="syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        later = make_packet(
            packet_id="later",
            sequence_number=110,
            payload=b"later",
        )
        earlier = make_packet(
            packet_id="earlier",
            sequence_number=100,
            payload=b"0123456789",
        )

        await packet_queue.put(syn)
        await packet_queue.put(later)
        await packet_queue.put(earlier)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            pipeline.feed.assert_called_once_with(
                b"0123456789later",
                connection_id=connection_id,
            )
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_skips_non_tcp_packets(packet_queue):
    async def run_test():
        pipeline = Mock()
        packet = make_packet(protocol="UDP")

        await packet_queue.put(packet)
        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)
            pipeline.feed.assert_not_called()
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_ignores_payload_without_syn(packet_queue):
    async def run_test():
        pipeline = Mock()
        packet = make_packet()

        await packet_queue.put(packet)
        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)
            pipeline.feed.assert_not_called()
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_cleans_up_on_rst(packet_queue):
    async def run_test():
        pipeline = Mock()
        syn = make_packet(
            packet_id="syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        rst = make_packet(
            packet_id="rst",
            payload=b"",
            sequence_number=100,
            tcp_flags=["RST"],
        )
        connection_id = build_connection_id(syn)

        await packet_queue.put(syn)
        await packet_queue.put(rst)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)
            pipeline.close_connection.assert_called_once_with(connection_id)
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_survives_http_parse_error(packet_queue):
    async def run_test():
        pipeline = Mock()
        pipeline.feed.side_effect = HTTPParseError("malformed HTTP")

        syn = make_packet(
            packet_id="syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        data = make_packet(sequence_number=100)

        await packet_queue.put(syn)
        await packet_queue.put(data)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            assert not task.done()
            pipeline.feed.assert_called_once()
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_cleanup_stale_streams_expires_only_inactive_connections(
    monkeypatch,
):
    async def run_test():
        pipeline = Mock()
        stop_event = asyncio.Event()

        stale_id = "TCP|10.0.0.1:1000->10.0.0.2:80"
        active_id = "TCP|10.0.0.3:2000->10.0.0.4:80"

        stale_stream = Mock()
        active_stream = Mock()
        streams = {
            stale_id: stale_stream,
            active_id: active_stream,
        }

        now = time.monotonic()
        last_seen = {
            stale_id: now - 60,
            active_id: now,
        }

        monkeypatch.setattr(
            worker_module,
            "TCP_GC_INTERVAL_SECONDS",
            0.01,
        )

        task = asyncio.create_task(
            worker_module._cleanup_stale_streams(
                streams,
                last_seen,
                pipeline,
                stop_event,
            )
        )

        try:
            for _ in range(50):
                if stale_id not in streams:
                    break
                await asyncio.sleep(0.01)

            assert stale_id not in streams
            assert stale_id not in last_seen
            assert active_id in streams
            assert active_id in last_seen

            pipeline.close_connection.assert_called_once_with(stale_id)
        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=1)

    import time
    asyncio.run(run_test())
