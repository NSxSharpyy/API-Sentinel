import asyncio
import logging

from app.http_pipeline import HTTPMessagePipeline
from app.http_reassembly import HTTPParseError
from app.queues import raw_packet_queue
from app.schemas import RawPacketChunk
from app.tcp_reassembly import TCPStreamReassembler

logger = logging.getLogger(__name__)

MAX_TCP_STREAMS = 10_000
MAX_TCP_BUFFERED_BYTES = 1_048_576


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


async def packet_worker(
    pipeline: HTTPMessagePipeline,
    stop_event: asyncio.Event,
) -> None:
    """Reassemble ordered TCP payloads before passing them to the HTTP parser."""
    streams: dict[str, TCPStreamReassembler] = {}
    logger.info("Packet worker started")

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

            # FIN and RST close this directional stream. Process any payload
            # carried by the packet before cleaning up its state.
            stream = streams.get(connection_id)

            if "SYN" in flags:
                if len(streams) >= MAX_TCP_STREAMS and connection_id not in streams:
                    logger.warning("TCP stream limit reached; skipping %s", connection_id)
                    continue

                stream = TCPStreamReassembler(
                    max_buffered_bytes=MAX_TCP_BUFFERED_BYTES
                )
                # SYN consumes one sequence number. The first payload byte,
                # if present, starts at sequence_number + 1.
                if packet.sequence_number is None:
                    logger.warning("SYN packet %s has no sequence number", packet.packet_id)
                    continue

                stream.reset(initial_sequence=packet.sequence_number + 1)
                streams[connection_id] = stream

            if stream is None:
                # Never guess an initial sequence number when capture begins
                # mid-connection. Wait for a SYN to establish sequence state.
                logger.debug(
                    "Skipping packet %s: no stream initialized by SYN",
                    packet.packet_id,
                )
                continue

            if packet.payload and packet.sequence_number is not None:
                payload_sequence = packet.sequence_number + (1 if "SYN" in flags else 0)
                try:
                    contiguous_payload = stream.feed(
                        payload_sequence,
                        packet.payload,
                    )
                except BufferError:
                    logger.warning("TCP reassembly buffer exceeded for %s", connection_id)
                    streams.pop(connection_id, None)
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

    # Clear retained parser/reassembly state on worker shutdown.
    for connection_id in streams:
        pipeline.close_connection(connection_id)
    streams.clear()
    logger.info("Packet worker stopped")