from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api_v1
from app.alert_bus import AlertBus
from app.database import Base
from app.main import app
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
    assert "persisted_count" in body["persistence"]
    assert body["detection"]["status"] == "running"
