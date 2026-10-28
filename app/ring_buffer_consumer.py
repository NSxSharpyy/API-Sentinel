import asyncio
import logging
import time
from collections.abc import AsyncIterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app import queues
from app.schemas import RawPacketChunk

logger = logging.getLogger(__name__)


@dataclass
class ConsumerStats:
    """Statistics for packet events processed by the consumer."""

    accepted: int = 0
    rejected: int = 0
    dropped: int = 0


async def consume_events(
    events: AsyncIterable[Mapping[str, Any]],
) -> ConsumerStats:
    """Validate decoded packet events and enqueue them without blocking."""
    stats = ConsumerStats()

    async for event in events:
        dispatch_started_ns = time.perf_counter_ns()
        reader_read_ns = event.get("_ring_buffer_read_at_ns")
        if (
            isinstance(reader_read_ns, int)
            and not isinstance(reader_read_ns, bool)
            and 0 < reader_read_ns <= dispatch_started_ns
        ):
            dispatch_started_ns = reader_read_ns
        try:
            packet = RawPacketChunk.model_validate(event)
        except ValidationError:
            stats.rejected += 1
            queues.rejected_packet_count += 1
            logger.warning("Rejected an invalid packet event")
            continue
        try:
            packet._queue_enqueued_at_ns = time.perf_counter_ns()
            queues.raw_packet_queue.put_nowait(packet)
        except asyncio.QueueFull:
            queues.dropped_packet_count += 1
            stats.dropped += 1
            logger.warning("Dropped packet because raw packet queue is full")
            continue

        queues.ring_buffer_dispatch_metrics.record(
            time.perf_counter_ns() - dispatch_started_ns
        )
        queues.record_raw_packet_queue_depth()
        stats.accepted += 1
        queues.accepted_packet_count += 1

        protocol = (packet.protocol or "").upper()
        if protocol == "TCP":
            queues.accepted_tcp_event_count += 1
        elif protocol == "UDP":
            queues.accepted_udp_event_count += 1
    return stats
