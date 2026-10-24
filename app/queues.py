
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

# Packet-event counters
dropped_packet_count = 0
accepted_packet_count = 0
rejected_packet_count = 0
accepted_tcp_event_count = 0
accepted_udp_event_count = 0

# TCP stream rejection and reassembly counters
tcp_stream_limit_rejection_count = 0
tcp_reassembly_buffer_overflow_count = 0

# TCP packet-processing diagnostic counters
tcp_packets_processed_count = 0
tcp_syn_packets_count = 0
tcp_payload_packets_count = 0
tcp_payload_bytes_count = 0
tcp_packets_without_stream_count = 0

# TCP payload delivery to the HTTP pipeline
tcp_payload_delivered_to_http_count = 0
tcp_payload_bytes_delivered_to_http_count = 0
