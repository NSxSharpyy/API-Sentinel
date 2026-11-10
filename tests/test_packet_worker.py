
import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

import app.packet_worker as worker_module
from app import queues
from app.http_reassembly import HTTPMessage, HTTPParseError
from app.packet_worker import build_connection_id
from app.schemas import RawPacketChunk


@pytest.fixture
def packet_queue(monkeypatch):
    """Provide an isolated packet queue and worker metrics for each test."""
    queue = asyncio.Queue(maxsize=100)
    monkeypatch.setattr(worker_module, "raw_packet_queue", queue)

    # Packet-worker metrics are module-level globals. Isolate them so worker
    # tests cannot leak counters into API tests or other test modules.
    counter_names = (
        "tcp_packets_processed_count",
        "tcp_syn_packets_count",
        "tcp_stream_limit_rejection_count",
        "tcp_half_closed_connection_limit_rejection_count",
        "tcp_packets_without_stream_count",
        "tcp_payload_packets_count",
        "tcp_payload_bytes_count",
        "tcp_reassembly_buffer_overflow_count",
        "tcp_payload_delivered_to_http_count",
        "tcp_payload_bytes_delivered_to_http_count",
    )
    for name in counter_names:
        monkeypatch.setattr(queues, name, 0)

    monkeypatch.setattr(
        queues, "raw_packet_queue_wait_metrics", queues.QueueWaitMetrics()
    )
    monkeypatch.setattr(
        queues,
        "tcp_stream_diagnostics",
        {"active_streams": 0, "reported_streams": 0, "streams": []},
        raising=False,
    )

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


def test_worker_cleans_up_both_directions_on_rst(packet_queue):
    async def run_test():
        pipeline = Mock()

        syn = make_packet(
            packet_id="syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        syn_ack = make_packet(
            packet_id="syn-ack",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            payload=b"",
            sequence_number=499,
            tcp_flags=["SYN", "ACK"],
        )
        rst = make_packet(
            packet_id="rst",
            payload=b"",
            sequence_number=100,
            tcp_flags=["RST"],
        )

        connection_id = build_connection_id(syn)

        for packet in (syn, syn_ack, rst):
            await packet_queue.put(packet)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            pipeline.close_connection.assert_called_once_with(
                connection_id, reason="tcp_rst"
            )
            assert queues.tcp_stream_diagnostics["active_streams"] == 0

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
    from app.http_pipeline import HTTPMessagePipeline
    from app.transaction_correlator import HTTPTransactionCorrelator

    async def run_test():
        correlator = HTTPTransactionCorrelator(
            request_ttl_seconds=60
        )

        pipeline = HTTPMessagePipeline(
            publisher=Mock(),
            correlator=correlator,
        )

        stop_event = asyncio.Event()

        stale_id = "TCP|10.0.0.1:1000->10.0.0.2:80"
        active_id = "TCP|10.0.0.3:2000->10.0.0.4:80"

        streams = {
            stale_id: Mock(),
            active_id: Mock(),
        }

        now = time.monotonic()

        last_seen = {
            stale_id: now - 60,
            active_id: now,
        }

        request = HTTPMessage(
            version="HTTP/1.1",
            message_type="request",
            connection_id=stale_id,
            method="GET",
            uri="/pending",
        )

        correlator.process(request)

        assert correlator.pending_request_count == 1

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

            assert correlator.pending_request_count == 0
            assert correlator.dropped_requests == 1

        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=1)

    asyncio.run(run_test())




def test_cleanup_expires_stale_requests_on_active_connections(
    monkeypatch,
):
    from app.http_pipeline import HTTPMessagePipeline
    from app.transaction_correlator import HTTPTransactionCorrelator

    async def run_test():
        correlator = HTTPTransactionCorrelator(
            request_ttl_seconds=0.03,
        )

        pipeline = HTTPMessagePipeline(
            publisher=Mock(),
            correlator=correlator,
        )

        stop_event = asyncio.Event()

        active_id = "TCP|10.0.0.3:2000->10.0.0.4:80"

        streams = {
            active_id: Mock(),
        }

        last_seen = {
            active_id: time.monotonic(),
        }

        request = HTTPMessage(
            version="HTTP/1.1",
            message_type="request",
            connection_id=active_id,
            method="GET",
            uri="/pending",
        )

        correlator.process(request)

        assert correlator.pending_request_count == 1

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
            for _ in range(100):
                if correlator.pending_request_count == 0:
                    break
                await asyncio.sleep(0.01)

            assert correlator.pending_request_count == 0
            assert correlator.dropped_requests == 1

            # The TCP connection must remain active.
            assert active_id in streams
            assert active_id in last_seen

        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=1)

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



def test_worker_bounds_half_closed_connections_without_evicting_active_stream(
    packet_queue, monkeypatch
):
    async def run_test():
        pipeline = Mock()
        pipeline.correlator.expire_stale_requests.return_value = 0

        monkeypatch.setattr(
            worker_module, "MAX_HALF_CLOSED_CONNECTIONS", 1
        )
        monkeypatch.setattr(
            queues, "tcp_half_closed_connection_limit_rejection_count", 0
        )

        first_fin = make_packet(
            packet_id="first-half-close",
            source_port=49152,
            payload=b"",
            sequence_number=99,
            tcp_flags=["FIN", "ACK"],
        )
        active_syn = make_packet(
            packet_id="unrelated-active-syn",
            source_port=49153,
            payload=b"",
            sequence_number=199,
            tcp_flags=["SYN"],
        )
        rejected_fin = make_packet(
            packet_id="rejected-half-close",
            source_port=49154,
            payload=b"",
            sequence_number=299,
            tcp_flags=["FIN", "ACK"],
        )

        active_connection_id = build_connection_id(active_syn)
        rejected_connection_id = build_connection_id(rejected_fin)

        for packet in (first_fin, active_syn, rejected_fin):
            await packet_queue.put(packet)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            assert queues.tcp_half_closed_connection_limit_rejection_count == 1

            # The newly rejected connection is explicitly closed.
            pipeline.close_connection.assert_called_once_with(
                rejected_connection_id,
                reason="tcp_half_close_state_limit",
            )

            # The previously tracked half-close and unrelated active stream
            # remain intact; the active stream was not silently evicted.
            diagnostics = queues.tcp_stream_diagnostics
            assert diagnostics["active_streams"] == 1
            assert diagnostics["streams"][0]["connection_id"] == (
                active_connection_id
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
            self,
            sequence_number,
            payload,
            captured_at,
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
                build_connection_id(syn),
                reason="tcp_reassembly_overflow",
            )

        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_records_raw_packet_queue_wait(packet_queue, monkeypatch):
    async def run_test():
        metrics = queues.QueueWaitMetrics()

        monkeypatch.setattr(
            queues,
            "raw_packet_queue_wait_metrics",
            metrics,
        )

        packet = make_packet(protocol="UDP")
        packet._queue_enqueued_at_ns = (
            time.perf_counter_ns() - 2_000_000
        )

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


def test_worker_resets_state_when_initial_syn_reuses_tuple(packet_queue):
    async def run_test():
        pipeline = Mock()
        connection_id = build_connection_id(make_packet())

        first_syn = make_packet(
            packet_id="first-syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        old_data = make_packet(
            packet_id="old-data",
            sequence_number=100,
            payload=b"GET /old HTTP/1.1\r\nHost: old.test\r\n",
        )
        reused_syn = make_packet(
            packet_id="reused-syn",
            payload=b"",
            sequence_number=499,
            tcp_flags=["SYN"],
        )
        new_data = make_packet(
            packet_id="new-data",
            sequence_number=500,
            payload=b"GET /new HTTP/1.1\r\nHost: new.test\r\n\r\n",
        )

        for packet in (
            first_syn,
            old_data,
            reused_syn,
            new_data,
        ):
            await packet_queue.put(packet)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            pipeline.close_connection.assert_called_once_with(
                connection_id, reason="tcp_tuple_reuse"
            )
            assert pipeline.feed.call_count == 2

        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_worker_preserves_stream_on_retransmitted_syn_ack(packet_queue):
    async def run_test():
        pipeline = Mock()

        client_syn = make_packet(
            packet_id="client-syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )

        server_syn_ack = make_packet(
            packet_id="server-syn-ack",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            payload=b"",
            sequence_number=499,
            tcp_flags=["SYN", "ACK"],
        )

        # Buffer the later segment first.
        later = make_packet(
            packet_id="server-later",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            sequence_number=505,
            payload=b"world",
        )

        # Retransmitted SYN-ACK must not reset the stream.
        retransmitted_syn_ack = make_packet(
            packet_id="server-syn-ack-retransmission",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            payload=b"",
            sequence_number=499,
            tcp_flags=["SYN", "ACK"],
        )

        # Fill the missing sequence range.
        earlier = make_packet(
            packet_id="server-earlier",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            sequence_number=500,
            payload=b"hello",
        )

        for packet in (
            client_syn,
            server_syn_ack,
            later,
            retransmitted_syn_ack,
            earlier,
        ):
            await packet_queue.put(packet)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            reverse_connection_id = build_connection_id(server_syn_ack)

            calls = pipeline.feed.call_args_list

            # The worker delivers contiguous chunks separately.
            assert len(calls) == 2

            delivered_payload = b"".join(
                call.args[0] for call in calls
            )

            assert delivered_payload == b"helloworld"

            for call in calls:
                assert (
                    call.kwargs["connection_id"]
                    == reverse_connection_id
                )

            # Retransmitted SYN-ACK must not close the connection.
            pipeline.close_connection.assert_not_called()

        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())

def test_worker_drains_accepted_packets_after_stop_is_set(packet_queue):
    async def run_test():
        pipeline = Mock()
        syn = make_packet(
            packet_id="shutdown-syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        data = make_packet(
            packet_id="shutdown-data",
            sequence_number=100,
        )

        await packet_queue.put(syn)
        await packet_queue.put(data)

        task, stop_event = start_worker(packet_queue, pipeline)
        stop_event.set()

        await asyncio.wait_for(task, timeout=2)
        await asyncio.wait_for(packet_queue.join(), timeout=1)

        assert packet_queue.empty()
        pipeline.feed.assert_called_once()
        assert pipeline.feed.call_args.args[0] == data.payload

    asyncio.run(run_test())

def test_worker_preserves_reverse_stream_after_one_sided_fin(packet_queue):
    async def run_test():
        pipeline = Mock()

        request_payload = (
            b"GET /pending HTTP/1.1\r\n"
            b"Host: example.test\r\n"
            b"\r\n"
        )
        response_payload = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 2\r\n"
            b"\r\n"
            b"OK"
        )

        client_syn = make_packet(
            packet_id="client-syn",
            payload=b"",
            sequence_number=99,
            tcp_flags=["SYN"],
        )
        server_syn_ack = make_packet(
            packet_id="server-syn-ack",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            payload=b"",
            sequence_number=499,
            tcp_flags=["SYN", "ACK"],
        )
        client_request = make_packet(
            packet_id="client-request",
            payload=request_payload,
            sequence_number=100,
            tcp_flags=["ACK"],
        )
        client_fin = make_packet(
            packet_id="client-fin",
            payload=b"",
            sequence_number=100 + len(request_payload),
            tcp_flags=["FIN", "ACK"],
        )
        server_response = make_packet(
            packet_id="server-response",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            payload=response_payload,
            sequence_number=500,
            tcp_flags=["ACK"],
        )
        server_fin = make_packet(
            packet_id="server-fin",
            source_ip="10.0.0.20",
            destination_ip="10.0.0.10",
            source_port=80,
            destination_port=49152,
            payload=b"",
            sequence_number=500 + len(response_payload),
            tcp_flags=["FIN", "ACK"],
        )

        client_connection_id = build_connection_id(client_syn)
        server_connection_id = build_connection_id(server_syn_ack)

        for packet in (
            client_syn,
            server_syn_ack,
            client_request,
            client_fin,
        ):
            await packet_queue.put(packet)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            # One FIN must not close the bidirectional HTTP connection.
            pipeline.close_connection.assert_not_called()
            assert queues.tcp_stream_diagnostics["active_streams"] == 1

            await packet_queue.put(server_response)
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            assert pipeline.feed.call_count == 2
            assert pipeline.feed.call_args_list[0].args[0] == request_payload
            assert pipeline.feed.call_args_list[1].args[0] == response_payload
            assert (
                pipeline.feed.call_args_list[1].kwargs["connection_id"]
                == server_connection_id
            )
            pipeline.close_connection.assert_not_called()

            await packet_queue.put(server_fin)
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            pipeline.close_connection.assert_called_once_with(
                server_connection_id,
                reason="tcp_fin_complete",
            )
            assert queues.tcp_stream_diagnostics["active_streams"] == 0

        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())

def test_worker_expires_half_closed_connection_without_reverse_stream(
    packet_queue, monkeypatch
):
    async def run_test():
        monkeypatch.setattr(worker_module, "TCP_STREAM_TTL_SECONDS", 0.03)
        monkeypatch.setattr(worker_module, "TCP_GC_INTERVAL_SECONDS", 0.01)

        pipeline = Mock()
        pipeline.correlator.expire_stale_requests.return_value = 0

        fin = make_packet(
            packet_id="fin-without-reverse-stream",
            payload=b"",
            tcp_flags=["FIN", "ACK"],
        )
        connection_id = build_connection_id(fin)
        await packet_queue.put(fin)

        task, stop_event = start_worker(packet_queue, pipeline)

        try:
            await asyncio.wait_for(packet_queue.join(), timeout=2)

            # The first FIN must be tracked even though no SYN or reverse
            # stream was observed. TTL cleanup must eventually close it.
            deadline = asyncio.get_running_loop().time() + 1.0
            while (
                not pipeline.close_connection.called
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)

            pipeline.close_connection.assert_called_once_with(
                connection_id, reason="tcp_idle_timeout"
            )

        finally:
            await stop_worker(task, stop_event)

    asyncio.run(run_test())


def test_fin_state_limit_preserves_same_connection_reverse_stream(
    monkeypatch,
):
    connection_fin = make_packet(
        packet_id="client-fin-at-capacity",
        source_ip="10.0.0.10",
        destination_ip="10.0.0.20",
        source_port=49152,
        destination_port=80,
        payload=b"",
        tcp_flags=["FIN", "ACK"],
    )
    connection_id = build_connection_id(connection_fin)
    _, reverse_id = worker_module._connection_directions(connection_id)

    reverse_stream = object()
    streams = {reverse_id: reverse_stream}
    last_seen = {
        connection_id: 10.0,
        reverse_id: 11.0,
    }

    existing_pair = frozenset((
        "TCP|192.0.2.1:1000->192.0.2.2:80",
        "TCP|192.0.2.2:80->192.0.2.1:1000",
    ))
    fin_seen = {
        existing_pair: {"TCP|192.0.2.1:1000->192.0.2.2:80"}
    }

    pipeline = Mock()
    monkeypatch.setattr(
        worker_module, "MAX_HALF_CLOSED_CONNECTIONS", 1
    )
    monkeypatch.setattr(
        queues, "tcp_half_closed_connection_limit_rejection_count", 0
    )

    result = worker_module._record_tcp_fin(
        connection_id,
        streams,
        last_seen,
        fin_seen,
        pipeline,
    )

    assert result is False
    assert queues.tcp_half_closed_connection_limit_rejection_count == 1

    # The FIN direction is removed, but the reverse response stream survives.
    assert connection_id not in streams
    assert streams[reverse_id] is reverse_stream
    assert connection_id not in last_seen
    assert reverse_id in last_seen

    # Existing half-close state is not evicted or replaced.
    assert len(fin_seen) == 1
    assert existing_pair in fin_seen
    pipeline.close_connection.assert_not_called()


def test_close_tcp_connection_preserves_state_when_pipeline_cleanup_fails():
    connection_id = build_connection_id(make_packet())
    directions = worker_module._connection_directions(connection_id)
    pair_key = frozenset(directions)

    streams = {
        direction: object()
        for direction in directions
    }
    last_seen = {
        direction: 10.0
        for direction in directions
    }
    fin_seen = {pair_key: {connection_id}}

    pipeline = Mock()
    pipeline.close_connection.side_effect = RuntimeError(
        "simulated pipeline cleanup failure"
    )

    with pytest.raises(RuntimeError, match="simulated pipeline cleanup failure"):
        worker_module._close_tcp_connection(
            connection_id,
            streams,
            last_seen,
            fin_seen,
            pipeline,
            reason="tcp_rst",
        )

    # Failed HTTP cleanup must not make the connection invisible to GC.
    assert set(streams) == set(directions)
    assert set(last_seen) == set(directions)
    assert fin_seen == {pair_key: {connection_id}}
    pipeline.close_connection.assert_called_once_with(
        connection_id,
        reason="tcp_rst",
    )
