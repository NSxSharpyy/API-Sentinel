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
    tcp_flags: Optional[list[str]] = None


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

class SecurityIncidentSchema(BaseModel):
    """Canonical cross-module representation of a persisted security incident."""

    incident_id: int = Field(gt=0)
    detected_at: datetime
    severity: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    source_ip: Optional[str] = Field(default=None, max_length=45)
    transaction_id: Optional[int] = Field(default=None, gt=0)
    endpoint_id: Optional[int] = Field(default=None, gt=0)
    status: str = Field(default="open", min_length=1, max_length=20)

    @classmethod
    def from_model(cls, incident):
        """Map SQLAlchemy's primary key `id` to the API field `incident_id`."""
        return cls(
            incident_id=incident.id,
            detected_at=incident.detected_at,
            severity=incident.severity,
            title=incident.title,
            description=incident.description,
            source_ip=incident.source_ip,
            transaction_id=incident.transaction_id,
            endpoint_id=incident.endpoint_id,
            status=incident.status,
        )
