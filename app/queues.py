
import asyncio

from app.schemas import HeaderData, PacketMetadata, RawPacketChunk

QUEUE_MAX_SIZE = 10000

raw_packet_queue: asyncio.Queue[RawPacketChunk] = asyncio.Queue(
    maxsize=QUEUE_MAX_SIZE
)
header_queue: asyncio.Queue[HeaderData] = asyncio.Queue(
    maxsize=QUEUE_MAX_SIZE
)
metadata_queue: asyncio.Queue[PacketMetadata] = asyncio.Queue(
    maxsize=QUEUE_MAX_SIZE
)

# Number of raw packets rejected because the queue was full.
dropped_packet_count = 0
