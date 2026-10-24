import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

import app.packet_worker as worker_module
from app import queues
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

            pipeline.feed.assert_called_once()
            args, kwargs = pipeline.feed.call_args
            assert args == (data.payload,)
            assert kwargs["connection_id"] == build_connection_id(data)
            assert kwargs["captured_at"] is not None
            assert kwargs["captured_at"].tzinfo is not None
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

            calls = pipeline.feed.call_args_list
            assert len(calls) == 2

            first_args, first_kwargs = calls[0]
            second_args, second_kwargs = calls[1]

            assert first_args == (b"0123456789",)
            assert second_args == (b"later",)

            assert first_kwargs["connection_id"] == connection_id
            assert second_kwargs["connection_id"] == connection_id

            assert first_kwargs["captured_at"] == earlier.captured_at
            assert second_kwargs["captured_at"] == later.captured_at
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

def test_worker_counts_tcp_stream_limit_rejections(
    packet_queue,
    monkeypatch,
):
    async def run_test():
        pipeline = Mock()
        monkeypatch.setattr(worker_module, "MAX_TCP_STREAMS", 1)
        monkeypatch.setattr(
            worker_module.queues,
            "tcp_stream_limit_rejection_count",
            0,
        )

        first_syn = make_packet(
            packet_id="syn-first",
            source_port=49152,
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        second_syn = make_packet(
            packet_id="syn-second",
            source_port=49153,
            payload=b"",
            sequence_number=199,
            tcp_flags=["SYN"],
        )

        await packet_queue.put(first_syn)
        await packet_queue.put(second_syn)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)
            assert (
                worker_module.queues.tcp_stream_limit_rejection_count
                == 1
            )
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())

def test_worker_counts_tcp_reassembly_buffer_overflows(
    packet_queue,
    monkeypatch,
):
    async def run_test():
        pipeline = Mock()
        monkeypatch.setattr(
            worker_module.queues,
            "tcp_reassembly_buffer_overflow_count",
            0,
        )

        def raise_buffer_error(
            self, sequence_number, payload, captured_at
        ):
            raise BufferError("test buffer overflow")

        monkeypatch.setattr(
            worker_module.TCPStreamReassembler,
            "feed_with_timestamps",
            raise_buffer_error,
        )

        syn = make_packet(
            packet_id="syn-overflow",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        data = make_packet(
            packet_id="data-overflow",
            sequence_number=100,
            payload=b"test",
        )

        await packet_queue.put(syn)
        await packet_queue.put(data)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)
            assert (
                worker_module.queues.tcp_reassembly_buffer_overflow_count
                == 1
            )
            pipeline.close_connection.assert_called_once_with(
                build_connection_id(syn)
            )
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_records_raw_packet_queue_wait(packet_queue, monkeypatch):
    async def run_test():
        metrics = queues.QueueWaitMetrics()
        monkeypatch.setattr(queues, "raw_packet_queue_wait_metrics", metrics)

        # UDP is consumed and skipped by the existing worker. It still must
        # contribute a queue-wait observation before protocol handling.
        packet = make_packet(protocol="UDP")
        packet._queue_enqueued_at_ns = time.perf_counter_ns() - 2_000_000
        await packet_queue.put(packet)

        pipeline = Mock()
        task, stop_event = start_worker(packet_queue, pipeline)
        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)
            snapshot = metrics.snapshot()
            assert snapshot["queue_wait_count"] == 1
            assert snapshot["queue_wait_sample_count"] == 1
            assert snapshot["last_queue_wait_ms"] > 0
            assert snapshot["p95_queue_wait_ms"] > 0
            pipeline.feed.assert_not_called()
        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_raw_packet_queue_wait_metrics_keep_bounded_samples():
    metrics = queues.QueueWaitMetrics(sample_capacity=2)
    metrics.record(1_000_000)
    metrics.record(2_000_000)
    metrics.record(3_000_000)

    snapshot = metrics.snapshot()
    assert snapshot["queue_wait_count"] == 3
    assert snapshot["queue_wait_sample_count"] == 2
    assert snapshot["average_queue_wait_ms"] == pytest.approx(2.0)
    assert snapshot["max_queue_wait_ms"] == pytest.approx(3.0)
    assert snapshot["p95_queue_wait_ms"] == pytest.approx(3.0)
