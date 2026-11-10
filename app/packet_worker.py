
import asyncio
import logging
import time

from app import queues
from app.http_pipeline import HTTPMessagePipeline, _reverse_connection_id
from app.http_reassembly import HTTPParseError
from app.queues import raw_packet_queue
from app.schemas import RawPacketChunk
from app.tcp_reassembly import TCPStreamReassembler

logger = logging.getLogger(__name__)

MAX_TCP_STREAMS = 10_000
MAX_HALF_CLOSED_CONNECTIONS = 10_000
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


def _connection_directions(connection_id: str) -> tuple[str, ...]:
    """Return both directional IDs for one bidirectional TCP connection."""
    reverse_id = _reverse_connection_id(connection_id)
    if reverse_id is None or reverse_id == connection_id:
        return (connection_id,)
    return (connection_id, reverse_id)


def _close_tcp_connection(
    connection_id: str,
    streams: dict[str, TCPStreamReassembler],
    last_seen: dict[str, float],
    fin_seen: dict[frozenset[str], set[str]],
    pipeline: HTTPMessagePipeline,
    reason: str = "tcp_connection_closed",
) -> None:
    """Remove both directional TCP streams and close HTTP connection state."""
    directions = _connection_directions(connection_id)

    # Close HTTP parser and correlation state first. If this fails, preserve
    # TCP tracking so the caller or stale-connection cleanup can retry.
    pipeline.close_connection(connection_id, reason=reason)

    for direction in directions:
        streams.pop(direction, None)
        last_seen.pop(direction, None)

    fin_seen.pop(frozenset(directions), None)


def _record_tcp_fin(
    connection_id: str,
    streams: dict[str, TCPStreamReassembler],
    last_seen: dict[str, float],
    fin_seen: dict[frozenset[str], set[str]],
    pipeline: HTTPMessagePipeline,
) -> bool:
    """Record one directional FIN; close only after both directions finish."""
    directions = _connection_directions(connection_id)
    pair_key = frozenset(directions)

    if (
        pair_key not in fin_seen
        and len(fin_seen) >= MAX_HALF_CLOSED_CONNECTIONS
    ):
        queues.tcp_half_closed_connection_limit_rejection_count += 1

        reverse_direction = next(
            (direction for direction in directions if direction != connection_id),
            None,
        )

        if reverse_direction in streams:
            # Tracking capacity is full, but the reverse stream must remain
            # available to deliver the HTTP response. Do not retain a new
            # half-close entry; the active reverse stream remains TTL-tracked.
            streams.pop(connection_id, None)
            last_seen.pop(connection_id, None)
            return False

        # No reverse stream can deliver a response, so reject and clean up
        # this new connection without evicting previously tracked state.
        _close_tcp_connection(
            connection_id,
            streams,
            last_seen,
            fin_seen,
            pipeline,
            reason="tcp_half_close_state_limit",
        )
        return False

    seen_directions = fin_seen.setdefault(pair_key, set())
    seen_directions.add(connection_id)

    # A FIN ends this direction, not the reverse direction. Retain its
    # timestamp so TTL cleanup can discover a half-closed connection even
    # when the reverse-direction stream was never initialized.
    streams.pop(connection_id, None)
    last_seen[connection_id] = time.monotonic()

    if all(direction in seen_directions for direction in directions):
        _close_tcp_connection(
            connection_id,
            streams,
            last_seen,
            fin_seen,
            pipeline,
            reason="tcp_fin_complete",
        )
        return True

    return False


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
    fin_seen: dict[frozenset[str], set[str]] | None = None,
) -> None:
    """Remove bidirectional TCP connections inactive beyond the configured TTL."""
    if fin_seen is None:
        fin_seen = {}
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

        stale_pairs: dict[frozenset[str], str] = {}

        # Include half-closed pairs even if one or both directional streams
        # have already been removed.
        for pair_key, seen_directions in list(fin_seen.items()):
            if pair_key:
                # Prefer a direction that actually sent FIN. Sorting makes
                # cleanup deterministic if more than one direction is stored.
                representative = (
                    min(seen_directions)
                    if seen_directions
                    else min(pair_key)
                )
                stale_pairs.setdefault(pair_key, representative)

        for connection_id in list(last_seen):
            pair_key = frozenset(_connection_directions(connection_id))
            stale_pairs.setdefault(pair_key, connection_id)

        for pair_key, representative in stale_pairs.items():
            # Activity in either direction keeps the whole connection alive.
            last_activity = max(
                (last_seen.get(direction, 0.0) for direction in pair_key),
                default=0.0,
            )
            if now - last_activity <= TCP_STREAM_TTL_SECONDS:
                continue

            try:
                _close_tcp_connection(
                    representative,
                    streams,
                    last_seen,
                    fin_seen,
                    pipeline,
                    reason="tcp_idle_timeout",
                )
            except Exception:
                logger.exception(
                    "Failed to close expired connection %s",
                    representative,
                )

            logger.debug(
                "Expired inactive TCP connection: %s",
                representative,
            )

        try:
            expired_requests = (
                pipeline.correlator.expire_stale_requests(now)
            )
            if expired_requests:
                logger.debug(
                    "Expired %s stale HTTP correlation requests",
                    expired_requests,
                )
        except Exception:
            logger.exception(
                "Failed to expire stale HTTP correlation requests"
            )

        _publish_tcp_stream_diagnostics(streams, last_seen)


async def packet_worker(
    pipeline: HTTPMessagePipeline,
    stop_event: asyncio.Event,
) -> None:
    """Reassemble ordered TCP payloads before passing them to the HTTP parser."""
    streams: dict[str, TCPStreamReassembler] = {}
    last_seen: dict[str, float] = {}
    fin_seen: dict[frozenset[str], set[str]] = {}

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
            fin_seen,
        )
    )

    logger.info("Packet worker started")

    try:
        while not stop_event.is_set() or not raw_packet_queue.empty():
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

                # Handle TCP SYN and SYN-ACK packets.
                if "SYN" in flags:
                    queues.tcp_syn_packets_count += 1

                    # A new initial SYN reusing an active connection
                    # tuple means the previous connection has ended.
                    if "ACK" not in flags:
                        directions = _connection_directions(connection_id)
                        pair_key = frozenset(directions)
                        previous_connection_exists = (
                            pair_key in fin_seen
                            or any(direction in streams for direction in directions)
                        )
                        if previous_connection_exists:
                            _close_tcp_connection(
                                connection_id,
                                streams,
                                last_seen,
                                fin_seen,
                                pipeline,
                                reason="tcp_tuple_reuse",
                            )
                            stream = None

                    # Initialize a new stream when necessary.
                    # Preserve an existing stream on a retransmitted SYN-ACK.
                    if stream is None or "ACK" not in flags:
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
                    # Terminal control packets must still clean up or update
                    # connection state even when their directional stream
                    # was already removed by an earlier FIN.
                    if "RST" in flags:
                        _close_tcp_connection(
                            connection_id,
                            streams,
                            last_seen,
                            fin_seen,
                            pipeline,
                            reason="tcp_rst",
                        )
                        _publish_tcp_stream_diagnostics(streams, last_seen)
                        continue

                    if "FIN" in flags:
                        _record_tcp_fin(
                            connection_id,
                            streams,
                            last_seen,
                            fin_seen,
                            pipeline,
                        )
                        _publish_tcp_stream_diagnostics(streams, last_seen)
                        continue

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

                        _close_tcp_connection(
                            connection_id,
                            streams,
                            last_seen,
                            fin_seen,
                            pipeline,
                            reason="tcp_reassembly_overflow",
                        )

                        _publish_tcp_stream_diagnostics(
                            streams,
                            last_seen,
                        )
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

                if "RST" in flags:
                    # Reset aborts the entire bidirectional connection.
                    _close_tcp_connection(
                        connection_id,
                        streams,
                        last_seen,
                        fin_seen,
                        pipeline,
                        reason="tcp_rst",
                    )
                elif "FIN" in flags:
                    # FIN closes only this sending direction. The reverse
                    # direction may still carry the HTTP response.
                    _record_tcp_fin(
                        connection_id,
                        streams,
                        last_seen,
                        fin_seen,
                        pipeline,
                    )

                _publish_tcp_stream_diagnostics(
                    streams,
                    last_seen,
                )

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

        closed_pairs: set[frozenset[str]] = set()
        cleanup_ids = list(streams)
        cleanup_ids.extend(
            next(iter(pair_key))
            for pair_key in list(fin_seen)
            if pair_key
        )

        for connection_id in cleanup_ids:
            pair_key = frozenset(_connection_directions(connection_id))
            if pair_key in closed_pairs:
                continue
            closed_pairs.add(pair_key)

            try:
                _close_tcp_connection(
                    connection_id,
                    streams,
                    last_seen,
                    fin_seen,
                    pipeline,
                    reason="worker_shutdown",
                )
            except Exception:
                logger.exception(
                    "Failed to close connection %s during shutdown",
                    connection_id,
                )

        streams.clear()
        last_seen.clear()
        fin_seen.clear()

        _publish_tcp_stream_diagnostics(
            streams,
            last_seen,
        )

        logger.info("Packet worker stopped")
