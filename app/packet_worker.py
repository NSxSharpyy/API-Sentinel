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

async def packet_worker(
    pipeline: HTTPMessagePipeline,
    stop_event: asyncio.Event,
) -> None:
    """Reassemble ordered TCP payloads before passing them to the HTTP parser."""
    streams: dict[str, TCPStreamReassembler] = {}
    last_seen: dict[str, float] = {}

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

            try:
                protocol = (packet.protocol or "TCP").upper()

                if protocol != "TCP":
                    logger.debug(
                        "Skipping non-TCP packet %s: protocol=%s",
                        packet.packet_id,
                        protocol,
                    )
                    continue

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
                    logger.debug(
                        "Skipping packet %s: no stream initialized by SYN",
                        packet.packet_id,
                    )
                    continue

                # Refresh activity for every packet on an initialized stream.
                last_seen[connection_id] = time.monotonic()

                if packet.payload and packet.sequence_number is not None:
                    payload_sequence = packet.sequence_number + (
                        1 if "SYN" in flags else 0
                    )

                    try:
                        contiguous_payload = stream.feed(
                            payload_sequence,
                            packet.payload,
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
                        continue

                    if contiguous_payload:
                        try:
                            pipeline.feed(
                                contiguous_payload,
                                connection_id=connection_id,
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
        # Stop the background cleanup task before clearing shared state.
        gc_task.cancel()

        try:
            await gc_task
        except asyncio.CancelledError:
            pass

        # Close all remaining parser/reassembly state on shutdown.
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
        logger.info("Packet worker stopped")
