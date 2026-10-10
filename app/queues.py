import asyncio

from app.schemas import HeaderData, PacketMetadata, RawPacketChunk


raw_packet_queue: asyncio.Queue[RawPacketChunk] = asyncio.Queue()
header_queue: asyncio.Queue[HeaderData] = asyncio.Queue()
metadata_queue: asyncio.Queue[PacketMetadata] = asyncio.Queue()