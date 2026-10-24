import asyncio
import logging
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
        try:
            packet = RawPacketChunk.model_validate(event)
        except ValidationError:
            stats.rejected += 1
            queues.rejected_packet_count += 1
            logger.warning("Rejected an invalid packet event")
            continue
        try:
            queues.raw_packet_queue.put_nowait(packet)
        except asyncio.QueueFull:
            queues.dropped_packet_count += 1
            stats.dropped += 1
            logger.warning("Dropped packet because raw packet queue is full")
            continue
        stats.accepted += 1
        queues.accepted_packet_count += 1

        protocol = (packet.protocol or "").upper()
        if protocol == "TCP":
            queues.accepted_tcp_event_count += 1
        elif protocol == "UDP":
            queues.accepted_udp_event_count += 1
    return stats
