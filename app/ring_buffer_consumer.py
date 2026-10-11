
import logging
from collections.abc import AsyncIterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.queues import raw_packet_queue
from app.schemas import RawPacketChunk

logger = logging.getLogger(__name__)


@dataclass
class ConsumerStats:
    accepted: int = 0
    rejected: int = 0


async def consume_events(
    events: AsyncIterable[Mapping[str, Any]],
) -> ConsumerStats:
    """
    Consume decoded packet events and put valid packets
    into the existing raw packet queue.

    The input is a temporary decoded-event interface.
    The real BPF adapter will be connected after the
    producer's event format is confirmed.
    """
    stats = ConsumerStats()

    async for event in events:
        try:
            packet = RawPacketChunk.model_validate(event)
        except ValidationError:
            stats.rejected += 1
            logger.warning("Rejected an invalid packet event")
            continue

        await raw_packet_queue.put(packet)
        stats.accepted += 1

    return stats
