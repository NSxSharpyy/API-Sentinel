import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.alert_bus import AlertBus
from app.database import Base
from app.http_reassembly import HTTPMessage
from app.models import SecurityIncident, TransactionLog
from app.schemas import SecurityIncidentSchema
from app.transaction_correlator import HTTPTransaction
from app.transaction_store import TransactionStore


@pytest.fixture
def store():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    yield TransactionStore(sessions)
    engine.dispose()


def make_txn(method, uri, headers, request_body, response_body, *,
             status=200, captured_at=None):
    port = 41000 if "/auth/login" in uri else 41001
    service_port = 5001 if "/auth/login" in uri else 5004
    request = HTTPMessage(
        version="HTTP/1.1", headers=headers,
        body=request_body.encode() if isinstance(request_body, str) else request_body,
        message_type="request", method=method, uri=uri,
        connection_id=f"TCP|127.0.0.1:{port}->127.0.0.1:{service_port}",
        captured_at=captured_at or datetime.now(timezone.utc) - timedelta(milliseconds=20),
    )
    response = HTTPMessage(
        version="HTTP/1.1", headers={"content-type": "application/json"},
        body=response_body.encode() if isinstance(response_body, str) else response_body,
        message_type="response", status_code=status, reason_phrase="OK",
        connection_id=f"TCP|127.0.0.1:{service_port}->127.0.0.1:{port}",
    )
    return HTTPTransaction(
        connection_key=f"TCP|127.0.0.1:{port}<->127.0.0.1:{service_port}",
        request=request, response=response,
    )


def login(store, token="demo-token", user_id=1):
    txn = make_txn(
        "POST", "/api/v2/auth/login",
        {"host": "127.0.0.1:5001", "content-type": "application/json"},
        json.dumps({"username": "alice", "password": "test-password"}),
        json.dumps({"token": token, "user_id": user_id, "token_type": "Bearer"}),
    )
    store.save(txn)


def invoice(token, invoice_id, owner_id, status=200):
    return make_txn(
        "GET", f"/api/v2/billing/invoices/{invoice_id}",
        {"host": "127.0.0.1:5004", "Authorization": f"Bearer {token}"},
        b"", json.dumps({"id": invoice_id, "owner_id": owner_id, "status": "paid"}),
        status=status,
    )


def test_cross_user_invoice_creates_linked_incident_and_redacts(store):
    login(store)
    invoice_id = store.save(invoice("demo-token", 3, 2))

    with store.session_factory() as session:
        incident = session.scalars(select(SecurityIncident)).one()
        record = session.get(TransactionLog, invoice_id)
        login_record = session.scalars(
            select(TransactionLog).where(
                TransactionLog.request_uri == "/api/v2/auth/login"
            )
        ).one()

    assert incident.transaction_id == invoice_id
    assert incident.severity == "high"
    assert "Potential BOLA" in incident.title
    assert record.request_headers["Authorization"] == "[REDACTED]"
    assert "demo-token" not in str(record.request_headers)
    assert json.loads(login_record.request_body)["password"] == "[REDACTED]"
    assert json.loads(login_record.response_body)["token"] == "[REDACTED]"
    metrics = store.bola_detector.snapshot()
    assert metrics["bola_detection_count"] == 1
    assert metrics["capture_to_detection_count"] == 1
    assert metrics["max_capture_to_detection_latency_ms"] > 0


def test_same_owner_invoice_does_not_create_incident(store):
    login(store)
    store.save(invoice("demo-token", 1, 1))

    with store.session_factory() as session:
        incidents = session.scalars(select(SecurityIncident)).all()
    assert incidents == []
    assert store.bola_detector.snapshot()["bola_detection_count"] == 0


def test_non_success_invoice_does_not_create_incident(store):
    login(store)
    store.save(invoice("demo-token", 3, 2, status=401))

    with store.session_factory() as session:
        incidents = session.scalars(select(SecurityIncident)).all()
    assert incidents == []


def test_cross_user_incident_is_published_after_commit(store):
    bus = AlertBus()
    subscriber = bus.subscribe()
    store.alert_bus = bus

    login(store)
    transaction_id = store.save(invoice("demo-token", 3, 2))
    event = subscriber.get_nowait()

    with store.session_factory() as session:
        incident = session.scalars(select(SecurityIncident)).one()
        transaction = session.get(TransactionLog, transaction_id)

    assert transaction is not None
    event_payload = event.to_dict()
    assert event.incident_id == incident.id
    assert event.transaction_id == transaction_id
    assert event.severity == "high"
    assert set(event_payload) == set(SecurityIncidentSchema.model_fields)
    assert event_payload["incident_id"] == incident.id
    assert event_payload["status"] == incident.status
    assert "Potential BOLA" in event.title
    assert event.source_ip == "127.0.0.1"
    assert bus.snapshot()["published_count"] == 1


def test_alert_delivery_failure_does_not_fail_persistence(store, caplog):
    bus = AlertBus()
    bus.close()
    store.alert_bus = bus

    login(store)
    transaction_id = store.save(invoice("demo-token", 3, 2))

    with store.session_factory() as session:
        transaction = session.get(TransactionLog, transaction_id)
        incidents = session.scalars(select(SecurityIncident)).all()

    assert transaction is not None
    assert len(incidents) == 1
    assert "Security incident persisted but alert publication failed" in caplog.text


def test_detected_incident_is_submitted_to_policy_after_commit(store):
    class RecordingPolicy:
        def __init__(self):
            self.outcomes = []

        def evaluate(self, outcome):
            self.outcomes.append(outcome)
            return {"accepted": False, "reason": "test_only"}

    policy = RecordingPolicy()
    store.blocklist_policy = policy

    login(store)
    transaction_id = store.save(invoice("demo-token", 3, 2))

    assert len(policy.outcomes) == 1
    outcome = policy.outcomes[0]
    assert outcome["detected"] is True
    incident_data = outcome["incident"]
    assert incident_data["transaction_id"] == transaction_id

    from app.models import SecurityIncident

    with store.session_factory() as session:
        persisted_incident = session.get(
            SecurityIncident, incident_data["incident_id"]
        )
    assert persisted_incident is not None


def test_policy_exception_does_not_hide_successful_persistence(store):
    class BrokenPolicy:
        def evaluate(self, outcome):
            raise RuntimeError("synthetic policy failure")

    store.blocklist_policy = BrokenPolicy()
    login(store)
    transaction_id = store.save(invoice("demo-token", 3, 2))

    from app.models import SecurityIncident, TransactionLog

    with store.session_factory() as session:
        transaction = session.get(TransactionLog, transaction_id)
        incidents = session.query(SecurityIncident).all()

    assert transaction is not None
    assert len(incidents) == 1
