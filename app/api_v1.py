"""Read-only REST API v1 for discovered endpoints, alerts, and metrics."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import queues
from app.database import SessionLocal
from app.models import DiscoveredEndpoint, SecurityIncident, TransactionLog
from app.schemas import SecurityIncidentSchema
from app.queues import header_queue, metadata_queue, raw_packet_queue

router = APIRouter(prefix="/api/v1", tags=["API v1"])


def _session_factory(request: Request):
    """Use the application store's DB configuration when initialized."""
    store = getattr(request.app.state, "transaction_store", None)
    factory = getattr(store, "session_factory", None)
    return factory if factory is not None else SessionLocal


def _endpoint_dict(endpoint: DiscoveredEndpoint) -> dict[str, Any]:
    return {
        "id": endpoint.id,
        "host": endpoint.host,
        "method": endpoint.method,
        "path": endpoint.path,
        "first_seen": endpoint.first_seen,
        "last_seen": endpoint.last_seen,
    }


def _incident_dict(incident: SecurityIncident) -> dict[str, Any]:
    """Serialize incidents using the shared cross-module schema."""
    return SecurityIncidentSchema.from_model(incident).model_dump(mode="json")


@router.get("/endpoints")
def list_endpoints(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List discovered API endpoints with bounded pagination."""
    with _session_factory(request)() as session:
        total = session.scalar(
            select(func.count()).select_from(DiscoveredEndpoint)
        ) or 0

        endpoints = session.scalars(
            select(DiscoveredEndpoint)
            .order_by(
                DiscoveredEndpoint.last_seen.desc(),
                DiscoveredEndpoint.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()

        return {
            "items": [_endpoint_dict(item) for item in endpoints],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/alerts")
def list_alerts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    severity: str | None = Query(default=None, min_length=1, max_length=16),
    status: str | None = Query(default=None, min_length=1, max_length=20),
):
    """List persisted security incidents, optionally filtered."""
    conditions = []
    if severity is not None:
        conditions.append(SecurityIncident.severity == severity)
    if status is not None:
        conditions.append(SecurityIncident.status == status)

    with _session_factory(request)() as session:
        count_query = select(func.count()).select_from(SecurityIncident)
        items_query = select(SecurityIncident)

        if conditions:
            count_query = count_query.where(*conditions)
            items_query = items_query.where(*conditions)

        total = session.scalar(count_query) or 0
        incidents = session.scalars(
            items_query
            .order_by(
                SecurityIncident.detected_at.desc(),
                SecurityIncident.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()

        return {
            "items": [_incident_dict(item) for item in incidents],
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {"severity": severity, "status": status},
        }


@router.get("/metrics")
def get_metrics(request: Request):
    """Expose current ingestion, persistence, detection, and alert metrics."""
    capture_task = getattr(request.app.state, "capture_task", None)
    persistence_worker = getattr(
        request.app.state, "persistence_worker", None
    )
    persistence_task = getattr(
        request.app.state, "persistence_worker_task", None
    )
    pipeline = getattr(request.app.state, "http_pipeline", None)
    store = getattr(request.app.state, "transaction_store", None)
    detector = getattr(store, "bola_detector", None)
    alert_bus = getattr(request.app.state, "alert_bus", None)

    with _session_factory(request)() as session:
        endpoint_count = session.scalar(
            select(func.count()).select_from(DiscoveredEndpoint)
        ) or 0
        transaction_count = session.scalar(
            select(func.count()).select_from(TransactionLog)
        ) or 0
        incident_count = session.scalar(
            select(func.count()).select_from(SecurityIncident)
        ) or 0
        open_incident_count = session.scalar(
            select(func.count())
            .select_from(SecurityIncident)
            .where(SecurityIncident.status == "open")
        ) or 0

    if detector is None:
        detection_metrics = {
            "status": "not_initialized",
            "bola_detection_count": 0,
            "capture_to_detection_count": 0,
        }
    else:
        detection_metrics = {
            "status": "running",
            **detector.snapshot(),
        }

    alert_metrics = (
        alert_bus.snapshot()
        if alert_bus is not None
        else {
            "closed": False,
            "subscriber_count": 0,
            "published_count": 0,
            "delivered_count": 0,
            "dropped_delivery_count": 0,
        }
    )
    alert_metrics.update({
        "total_incidents": incident_count,
        "open_incidents": open_incident_count,
    })

    return {
        "ingestion": {
            "raw_packet_queue": raw_packet_queue.qsize(),
            "header_queue": header_queue.qsize(),
            "metadata_queue": metadata_queue.qsize(),
            "accepted_packet_count": queues.accepted_packet_count,
            "accepted_tcp_event_count": queues.accepted_tcp_event_count,
            "accepted_udp_event_count": queues.accepted_udp_event_count,
            "rejected_packet_count": queues.rejected_packet_count,
            "dropped_packet_count": queues.dropped_packet_count,
            "capture_running": (
                capture_task is not None and not capture_task.done()
                and getattr(request.app.state, "capture_status", None) == "running"
            ),
        },
        "persistence": {
            "queue_depth": (
                persistence_worker.queue.qsize()
                if persistence_worker is not None else 0
            ),
            "queue_wait_count": (
                persistence_worker.queue_wait_count
                if persistence_worker is not None else 0
            ),
            "queue_wait_sample_count": (
                persistence_worker.queue_wait_sample_count
                if persistence_worker is not None else 0
            ),
            "last_queue_wait_ms": (
                persistence_worker.last_queue_wait_ms
                if persistence_worker is not None else 0.0
            ),
            "average_queue_wait_ms": (
                persistence_worker.average_queue_wait_ms
                if persistence_worker is not None else 0.0
            ),
            "max_queue_wait_ms": (
                persistence_worker.max_queue_wait_ms
                if persistence_worker is not None else 0.0
            ),
            "p95_queue_wait_ms": (
                persistence_worker.p95_queue_wait_ms
                if persistence_worker is not None else 0.0
            ),
            "persisted_count": (
                persistence_worker.persisted_count
                if persistence_worker is not None else 0
            ),
            "failed_count": (
                persistence_worker.failed_count
                if persistence_worker is not None else 0
            ),
            "rejected_count": (
                persistence_worker.rejected_count
                if persistence_worker is not None else 0
            ),
            "worker_running": (
                persistence_task is not None and not persistence_task.done()
            ),
        },
        "processing": {
            "completed_transactions": (
                len(pipeline.completed_transactions)
                if pipeline is not None else 0
            ),
            "last_transaction_processing_latency_ms": (
                pipeline.last_transaction_processing_latency_ms
                if pipeline is not None else 0.0
            ),
            "average_transaction_processing_latency_ms": (
                pipeline.average_transaction_processing_latency_ms
                if pipeline is not None else 0.0
            ),
            "max_transaction_processing_latency_ms": (
                pipeline.max_transaction_processing_latency_ms
                if pipeline is not None else 0.0
            ),
        },
        "detection": detection_metrics,
        "alerts": alert_metrics,
        "database": {
            "discovered_endpoints": endpoint_count,
            "transaction_logs": transaction_count,
            "security_incidents": incident_count,
        },
    }
