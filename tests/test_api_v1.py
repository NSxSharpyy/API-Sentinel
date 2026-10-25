from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api_v1, queues
from app.alert_bus import AlertBus
from app.database import Base
from app.main import app
from app.schemas import SecurityIncidentSchema
from app.security_detection import BOLADetector
from app.models import (
    DiscoveredEndpoint,
    SecurityIncident,
    TransactionLog,
)


@pytest.fixture
def api_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    # Inject only the in-memory test DB; never use the project's real DB.
    monkeypatch.setattr(
        app.state,
        "transaction_store",
        SimpleNamespace(
            session_factory=sessions,
            bola_detector=BOLADetector(),
        ),
        raising=False,
    )
    monkeypatch.setattr(app.state, "alert_bus", AlertBus(), raising=False)

    client = TestClient(app)
    yield client, sessions
    engine.dispose()


def seed_endpoint(session, host, method, path, last_seen):
    endpoint = DiscoveredEndpoint(
        host=host,
        method=method,
        path=path,
        first_seen=last_seen - timedelta(days=1),
        last_seen=last_seen,
    )
    session.add(endpoint)
    session.flush()
    return endpoint


def test_endpoints_support_pagination(api_client):
    client, sessions = api_client
    with sessions() as session:
        seed_endpoint(
            session, "api.example.test", "GET", "/older",
            datetime(2026, 10, 22, tzinfo=timezone.utc),
        )
        seed_endpoint(
            session, "api.example.test", "POST", "/newer",
            datetime(2026, 10, 23, tzinfo=timezone.utc),
        )
        session.commit()

    response = client.get("/api/v1/endpoints?limit=1&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["path"] == "/newer"

    second = client.get("/api/v1/endpoints?limit=1&offset=1")
    assert second.status_code == 200
    assert second.json()["items"][0]["path"] == "/older"


def test_alerts_support_filters_and_pagination(api_client):
    client, sessions = api_client
    with sessions() as session:
        session.add_all([
            SecurityIncident(
                detected_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
                severity="high",
                title="BOLA alert",
                source_ip="192.0.2.10",
                status="open",
            ),
            SecurityIncident(
                detected_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
                severity="high",
                title="Second BOLA alert",
                status="open",
            ),
            SecurityIncident(
                detected_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
                severity="low",
                title="Informational alert",
                status="closed",
            ),
        ])
        session.commit()

    response = client.get(
        "/api/v1/alerts?severity=high&status=open&limit=1"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "BOLA alert"
    assert body["items"][0]["severity"] == "high"
    assert body["items"][0]["incident_id"] > 0
    assert "id" not in body["items"][0]
    assert set(body["items"][0]) == set(SecurityIncidentSchema.model_fields)
    assert body["filters"] == {"severity": "high", "status": "open"}


def test_api_pagination_rejects_invalid_bounds(api_client):
    client, _ = api_client

    assert client.get("/api/v1/endpoints?limit=0").status_code == 422
    assert client.get("/api/v1/endpoints?limit=101").status_code == 422
    assert client.get("/api/v1/alerts?offset=-1").status_code == 422


def test_metrics_expose_database_and_alert_bus_counts(api_client):
    client, sessions = api_client
    with sessions() as session:
        endpoint = seed_endpoint(
            session, "api.example.test", "GET", "/invoices",
            datetime(2026, 10, 23, tzinfo=timezone.utc),
        )
        transaction = TransactionLog(
            endpoint=endpoint,
            timestamp=datetime(2026, 10, 23, tzinfo=timezone.utc),
            source_ip="192.0.2.10",
            request_method="GET",
            request_uri="/invoices",
            response_status=200,
        )
        session.add(transaction)
        session.flush()
        session.add(SecurityIncident(
            endpoint_id=endpoint.id,
            transaction_id=transaction.id,
            detected_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
            severity="high",
            title="Test incident",
            source_ip="192.0.2.10",
            status="open",
        ))
        session.commit()

    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == {
        "discovered_endpoints": 1,
        "transaction_logs": 1,
        "security_incidents": 1,
    }
    assert body["alerts"]["total_incidents"] == 1
    assert body["alerts"]["open_incidents"] == 1
    assert body["alerts"]["published_count"] == 0
    assert "accepted_packet_count" in body["ingestion"]
    assert body["ingestion"]["raw_packet_queue_capacity"] == (
        api_v1.raw_packet_queue.maxsize
    )
    assert body["ingestion"]["raw_packet_queue_max_depth"] == (
        queues.raw_packet_queue_max_depth
    )
    packet_wait = body["ingestion"]["raw_packet_queue_wait"]
    assert packet_wait["queue_wait_count"] >= 0
    assert "p95_queue_wait_ms" in packet_wait
    assert "persisted_count" in body["persistence"]
    assert "queue_wait_count" in body["persistence"]
    assert "queue_wait_sample_count" in body["persistence"]
    assert "average_queue_wait_ms" in body["persistence"]
    assert "p95_queue_wait_ms" in body["persistence"]
    assert body["detection"]["status"] == "running"


def test_persisted_http_transaction_populates_discovered_endpoint_api(api_client, monkeypatch):
    from app.http_reassembly import HTTPMessage
    from app.transaction_correlator import HTTPTransaction
    from app.transaction_store import TransactionStore

    client, sessions = api_client
    bus = app.state.alert_bus
    store = TransactionStore(session_factory=sessions, alert_bus=bus)
    monkeypatch.setattr(app.state, "transaction_store", store, raising=False)

    request = HTTPMessage(
        version="HTTP/1.1",
        headers={"Host": "API.Example.Test", "Content-Type": "application/json"},
        body=b"{}",
        message_type="request",
        method="POST",
        uri="/v1/users?source=lab",
        connection_id="TCP|192.0.2.10:49152->192.0.2.20:443",
        captured_at=datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc),
    )
    response = HTTPMessage(
        version="HTTP/1.1",
        headers={"content-type": "application/json"},
        body=b'{"created":true}',
        message_type="response",
        status_code=201,
        reason_phrase="Created",
        connection_id="TCP|192.0.2.20:443->192.0.2.10:49152",
    )
    transaction = HTTPTransaction(
        connection_key="TCP|192.0.2.10:49152<->192.0.2.20:443",
        request=request,
        response=response,
    )
    store.save(transaction)

    listing = client.get("/api/v1/endpoints")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["host"] == "api.example.test"
    assert body["items"][0]["method"] == "POST"
    assert body["items"][0]["path"] == "/v1/users"

    metrics = client.get("/api/v1/metrics").json()
    assert metrics["database"]["discovered_endpoints"] == 1
    assert metrics["database"]["transaction_logs"] == 1
