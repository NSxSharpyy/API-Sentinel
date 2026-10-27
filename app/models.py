from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class DiscoveredEndpoint(Base):
    __tablename__ = "discovered_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "host", "method", "path",
            name="uq_endpoint_host_method_path",
        ),
        Index("ix_endpoint_last_seen", "last_seen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    transactions: Mapped[list["TransactionLog"]] = relationship(
        back_populates="endpoint"
    )
    incidents: Mapped[list["SecurityIncident"]] = relationship(
        back_populates="endpoint"
    )


class TransactionLog(Base):
    __tablename__ = "transaction_logs"
    __table_args__ = (
        Index("ix_transaction_timestamp", "timestamp"),
        Index("ix_transaction_source_ip", "source_ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovered_endpoints.id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    source_ip: Mapped[str | None] = mapped_column(String(45))
    destination_ip: Mapped[str | None] = mapped_column(String(45))
    request_method: Mapped[str | None] = mapped_column(String(16))
    request_uri: Mapped[str | None] = mapped_column(String(4096))
    response_status: Mapped[int | None] = mapped_column(Integer)
    request_headers: Mapped[dict | None] = mapped_column(JSON)
    response_headers: Mapped[dict | None] = mapped_column(JSON)
    request_body: Mapped[str | None] = mapped_column(Text)
    response_body: Mapped[str | None] = mapped_column(Text)

    endpoint: Mapped["DiscoveredEndpoint | None"] = relationship(
        back_populates="transactions"
    )
    incidents: Mapped[list["SecurityIncident"]] = relationship(
        back_populates="transaction"
    )


class BlockedTransactionAudit(Base):
    """Audit record for a packet actually dropped by kernel enforcement."""

    __tablename__ = "blocked_transaction_audits"
    __table_args__ = (
        Index("ix_blocked_audit_dropped_at", "dropped_at"),
        Index("ix_blocked_audit_attacker_time", "attacker_ip", "dropped_at"),
        Index("ix_blocked_audit_rule_id", "rule_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dropped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    attacker_identifier: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    attacker_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    target_endpoint: Mapped[str] = mapped_column(String(320), nullable=False)
    target_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    source_port: Mapped[int] = mapped_column(Integer, nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(8), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    interface_index: Mapped[int] = mapped_column(Integer, nullable=False)


class SecurityIncident(Base):
    __tablename__ = "security_incidents"
    __table_args__ = (
        Index("ix_incident_detected_at", "detected_at"),
        Index("ix_incident_severity_status", "severity", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovered_endpoints.id"), nullable=True
    )
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transaction_logs.id"), nullable=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(String(45))
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False
    )

    endpoint: Mapped["DiscoveredEndpoint | None"] = relationship(
        back_populates="incidents"
    )
    transaction: Mapped["TransactionLog | None"] = relationship(
        back_populates="incidents"
    )
