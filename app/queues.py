
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
# Cumulative packet-event counters for this application process.
accepted_packet_count = 0
rejected_packet_count = 0
# TCP streams rejected because the active-stream limit was reached.
tcp_stream_limit_rejection_count = 0

# TCP streams discarded because their reassembly buffer exceeded its limit.
tcp_reassembly_buffer_overflow_count = 0
