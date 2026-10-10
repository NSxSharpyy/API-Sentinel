from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RawPacketChunk(BaseModel):
    """One raw packet chunk from the ingestion layer."""

    packet_id: str = Field(min_length=1)
    captured_at: datetime
    payload: bytes

    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None

    source_port: Optional[int] = Field(default=None, ge=0, le=65535)
    destination_port: Optional[int] = Field(default=None, ge=0, le=65535)

    protocol: Optional[str] = None
    sequence_number: Optional[int] = Field(default=None, ge=0)


class HeaderData(BaseModel):
    """One HTTP header name/value pair."""

    name: str = Field(min_length=1)
    value: str


class PacketMetadata(BaseModel):
    """Additional metadata associated with a packet."""

    packet_id: str = Field(min_length=1)
    captured_at: datetime

    interface: Optional[str] = None
    direction: Optional[str] = None
    connection_id: Optional[str] = None
    tcp_flags: Optional[list[str]] = None