
import asyncio
import logging
import time

from app import queues
from app.http_pipeline import HTTPMessagePipeline
from app.http_reassembly import HTTPParseError
from app.queues import raw_packet_queue
from app.schemas import RawPacketChunk
from app.tcp_reassembly import TCPStreamReassembler

logger = logging.getLogger(__name__)

MAX_TCP_STREAMS = 10_000
MAX_TCP_BUFFERED_BYTES = 1_048_576
TCP_STREAM_TTL_SECONDS = 30.0
TCP_GC_INTERVAL_SECONDS = 5.0
MAX_DIAGNOSTIC_STREAMS = 100


def build_connection_id(packet: RawPacketChunk) -> str | None:
    """Build a directional connection key from a packet's 4-tuple."""
    if (
        packet.source_ip is None
        or packet.destination_ip is None
        or packet.source_port is None
        or packet.destination_port is None
    ):
        return None

    protocol = (packet.protocol or "TCP").upper()

    return (
        f"{protocol}|"
        f"{packet.source_ip}:{packet.source_port}->"
        f"{packet.destination_ip}:{packet.destination_port}"
    )


def _flags(packet: RawPacketChunk) -> set[str]:
    """Normalize TCP flag names."""
    return {flag.strip().upper() for flag in (packet.tcp_flags or [])}


def _publish_tcp_stream_diagnostics(
    streams: dict[str, TCPStreamReassembler],
    last_seen: dict[str, float],
) -> None:
    """Publish a bounded, read-only snapshot of active TCP stream state."""
    stream_details = []

    for connection_id, stream in list(streams.items())[
        :MAX_DIAGNOSTIC_STREAMS
    ]:
        pending = getattr(stream, "pending", {})
        if not isinstance(pending, dict):
            pending = {}

        next_sequence = getattr(stream, "next_sequence", None)
        buffered_bytes = getattr(stream, "buffered_bytes", 0)

        stream_details.append(
            {
                "connection_id": connection_id,
                "next_expected_sequence": (
                    next_sequence
                    if isinstance(next_sequence, int)
                    else None
                ),
                "buffered_bytes": (
                    buffered_bytes
                    if isinstance(buffered_bytes, int)
                    else 0
                ),
                "pending_segment_count": len(pending),
                "pending_sequence_numbers": sorted(pending.keys())[:20],
                "last_seen_monotonic": last_seen.get(connection_id),
            }
        )

    queues.tcp_stream_diagnostics = {
        "active_streams": len(streams),
        "reported_streams": len(stream_details),
        "streams": stream_details,
    }


async def _cleanup_stale_streams(
    streams: dict[str, TCPStreamReassembler],
    last_seen: dict[str, float],
    pipeline: HTTPMessagePipeline,
    stop_event: asyncio.Event,
) -> None:
    """Remove TCP streams inactive for longer than the configured TTL."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=TCP_GC_INTERVAL_SECONDS,
            )
            break
        except asyncio.TimeoutError:
            pass

        now = time.monotonic()
        stale_ids = [
            connection_id
            for connection_id, last_activity in list(last_seen.items())
            if now - last_activity > TCP_STREAM_TTL_SECONDS
        ]

        for connection_id in stale_ids:
            streams.pop(connection_id, None)
            last_seen.pop(connection_id, None)

            try:
                pipeline.close_connection(connection_id)
            except Exception:
                logger.exception(
                    "Failed to close expired connection %s",
                    connection_id,
                )

            logger.debug("Expired inactive TCP stream: %s", connection_id)

        _publish_tcp_stream_diagnostics(streams, last_seen)


async def packet_worker(
    pipeline: HTTPMessagePipeline,
    stop_event: asyncio.Event,
) -> None:
    """Reassemble ordered TCP payloads before passing them to the HTTP parser."""
    streams: dict[str, TCPStreamReassembler] = {}
    last_seen: dict[str, float] = {}

    queues.tcp_stream_diagnostics = {
        "active_streams": 0,
        "reported_streams": 0,
        "streams": [],
    }

    gc_task = asyncio.create_task(
        _cleanup_stale_streams(
            streams,
            last_seen,
            pipeline,
            stop_event,
        )
    )

    logger.info("Packet worker started")

    try:
        while not stop_event.is_set():
            try:
                packet = await asyncio.wait_for(
                    raw_packet_queue.get(),
                    timeout=0.5,
                )
            except asyncio.TimeoutError:
                continue

            queued_at_ns = packet._queue_enqueued_at_ns
            if queued_at_ns is not None:
                queues.raw_packet_queue_wait_metrics.record(
                    time.perf_counter_ns() - queued_at_ns
                )

            try:
                protocol = (packet.protocol or "TCP").upper()

                if protocol != "TCP":
                    logger.debug(
                        "Skipping non-TCP packet %s: protocol=%s",
                        packet.packet_id,
                        protocol,
                    )
                    continue

                queues.tcp_packets_processed_count += 1

                connection_id = build_connection_id(packet)

                if connection_id is None:
                    logger.debug(
                        "Skipping packet %s: missing connection tuple",
                        packet.packet_id,
                    )
                    continue

                flags = _flags(packet)
                stream = streams.get(connection_id)

                if "SYN" in flags:
                    queues.tcp_syn_packets_count += 1

                    if (
                        len(streams) >= MAX_TCP_STREAMS
                        and connection_id not in streams
                    ):
                        logger.warning(
                            "TCP stream limit reached; skipping %s",
                            connection_id,
                        )
                        queues.tcp_stream_limit_rejection_count += 1
                        continue

                    if packet.sequence_number is None:
                        logger.warning(
                            "SYN packet %s has no sequence number",
                            packet.packet_id,
                        )
                        continue

                    stream = TCPStreamReassembler(
                        max_buffered_bytes=MAX_TCP_BUFFERED_BYTES
                    )
                    stream.reset(
                        initial_sequence=packet.sequence_number + 1
                    )

                    streams[connection_id] = stream
                    last_seen[connection_id] = time.monotonic()

                if stream is None:
                    queues.tcp_packets_without_stream_count += 1
                    logger.debug(
                        "Skipping packet %s: no stream initialized by SYN",
                        packet.packet_id,
                    )
                    continue

                last_seen[connection_id] = time.monotonic()

                if packet.payload and packet.sequence_number is not None:
                    queues.tcp_payload_packets_count += 1
                    queues.tcp_payload_bytes_count += len(packet.payload)

                    payload_sequence = packet.sequence_number + (
                        1 if "SYN" in flags else 0
                    )

                    try:
                        timestamped_chunks = stream.feed_with_timestamps(
                            payload_sequence,
                            packet.payload,
                            packet.captured_at,
                        )
                    except BufferError:
                        logger.warning(
                            "TCP reassembly buffer exceeded for %s",
                            connection_id,
                        )
                        queues.tcp_reassembly_buffer_overflow_count += 1
                        streams.pop(connection_id, None)
                        last_seen.pop(connection_id, None)
                        pipeline.close_connection(connection_id)
                        _publish_tcp_stream_diagnostics(streams, last_seen)
                        continue

                    if timestamped_chunks:
                        contiguous_payload = b"".join(
                            chunk for chunk, _ in timestamped_chunks
                        )
                        queues.tcp_payload_delivered_to_http_count += 1
                        queues.tcp_payload_bytes_delivered_to_http_count += (
                            len(contiguous_payload)
                        )

                        try:
                            for chunk, captured_at in timestamped_chunks:
                                pipeline.feed(
                                    chunk,
                                    connection_id=connection_id,
                                    captured_at=captured_at,
                                )
                        except HTTPParseError as exc:
                            logger.warning(
                                "Malformed HTTP stream for connection %s: %s",
                                connection_id,
                                exc,
                            )

                if "FIN" in flags or "RST" in flags:
                    streams.pop(connection_id, None)
                    last_seen.pop(connection_id, None)
                    pipeline.close_connection(connection_id)

                _publish_tcp_stream_diagnostics(streams, last_seen)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Failed to process packet %s",
                    getattr(packet, "packet_id", "unknown"),
                )
            finally:
                raw_packet_queue.task_done()

    finally:
        gc_task.cancel()

        try:
            await gc_task
        except asyncio.CancelledError:
            pass

        for connection_id in list(streams):
            try:
                pipeline.close_connection(connection_id)
            except Exception:
                logger.exception(
                    "Failed to close connection %s during shutdown",
                    connection_id,
                )

        streams.clear()
        last_seen.clear()
        _publish_tcp_stream_diagnostics(streams, last_seen)
        logger.info("Packet worker stopped")
