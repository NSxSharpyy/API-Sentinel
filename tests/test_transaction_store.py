from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import DiscoveredEndpoint, SecurityIncident, TransactionLog
from app.http_reassembly import HTTPMessage
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
    test_sessions = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    yield TransactionStore(test_sessions)
    engine.dispose()


def make_transaction():
    request = HTTPMessage(
        version="HTTP/1.1",
        headers={"host": "example.test"},
        body=b"",
        message_type="request",
        method="GET",
        uri="/health",
        connection_id="TCP|10.0.0.10:49152->10.0.0.20:80",
    )
    response = HTTPMessage(
        version="HTTP/1.1",
        headers={"content-type": "text/plain"},
        body=b"OK",
        message_type="response",
        status_code=200,
        reason_phrase="OK",
        connection_id="TCP|10.0.0.20:80->10.0.0.10:49152",
    )
    return HTTPTransaction(
        connection_key="TCP|10.0.0.10:49152<->10.0.0.20:80",
        request=request,
        response=response,
    )


def test_save_persists_http_transaction(store):
    transaction = make_transaction()
    captured_at = datetime(2026, 10, 23, 9, 30, tzinfo=timezone.utc)
    transaction.request.captured_at = captured_at

    transaction_id = store.save(transaction)

    with store.session_factory() as session:
        record = session.get(TransactionLog, transaction_id)

    assert record is not None
    assert record.timestamp.replace(tzinfo=timezone.utc) == captured_at
    assert record.source_ip == "10.0.0.10"
    assert record.destination_ip == "10.0.0.20"
    assert record.request_method == "GET"
    assert record.request_uri == "/health"
    assert record.response_status == 200
    assert record.request_headers == {"host": "example.test"}
    assert record.response_headers == {"content-type": "text/plain"}
    assert record.response_body == "OK"

def test_save_returns_unique_ids(store):
    first_id = store.save(make_transaction())
    second_id = store.save(make_transaction())

    assert first_id != second_id

    with store.session_factory() as session:
        records = session.scalars(
            select(TransactionLog).order_by(TransactionLog.id)
        ).all()

    assert len(records) == 2


def test_save_rolls_back_when_commit_fails(store, monkeypatch):
    def fail_commit(self):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(
        store.session_factory.class_,
        "commit",
        fail_commit,
    )

    with pytest.raises(RuntimeError, match="simulated database failure"):
        store.save(make_transaction())

    with store.session_factory() as session:
        records = session.scalars(select(TransactionLog)).all()

    assert records == []


def test_save_discovers_endpoint_normalizes_host_and_strips_query(store):
    first = make_transaction()
    first.request.headers = {"Host": "EXAMPLE.TEST"}
    first.request.uri = "/health?probe=one"
    first.request.captured_at = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

    first_id = store.save(first)

    second = make_transaction()
    second.request.headers = {"host": "example.test"}
    second.request.uri = "/health?probe=two"
    second.request.captured_at = datetime(2026, 10, 25, 12, 1, tzinfo=timezone.utc)
    second_id = store.save(second)

    with store.session_factory() as session:
        endpoints = session.scalars(select(DiscoveredEndpoint)).all()
        first_record = session.get(TransactionLog, first_id)
        second_record = session.get(TransactionLog, second_id)

    assert len(endpoints) == 1
    endpoint = endpoints[0]
    assert (endpoint.host, endpoint.method, endpoint.path) == (
        "example.test", "GET", "/health"
    )
    assert first_record.endpoint_id == endpoint.id
    assert second_record.endpoint_id == endpoint.id
    assert endpoint.first_seen.replace(tzinfo=timezone.utc) == first.request.captured_at
    assert endpoint.last_seen.replace(tzinfo=timezone.utc) == second.request.captured_at


def test_bola_incident_links_to_discovered_endpoint(store):
    login = make_transaction()
    login.request.method = "POST"
    login.request.uri = "/api/v2/auth/login"
    login.request.headers = {"host": "billing.example.test", "content-type": "application/json"}
    login.request.body = b'{"username":"user-a","password":"test"}'
    login.response.status_code = 200
    login.response.body = b'{"token":"test-token","user_id":1}'
    store.save(login)

    invoice = make_transaction()
    invoice.request.uri = "/api/v2/billing/invoices/42"
    invoice.request.headers = {
        "host": "billing.example.test",
        "authorization": "Bearer test-token",
    }
    invoice.response.status_code = 200
    invoice.response.body = b'{"id":42,"owner_id":2,"status":"paid"}'
    transaction_id = store.save(invoice)

    with store.session_factory() as session:
        record = session.get(TransactionLog, transaction_id)
        incident = session.scalar(select(SecurityIncident))
        endpoint = session.get(DiscoveredEndpoint, record.endpoint_id)

    assert incident is not None
    assert incident.transaction_id == record.id
    assert incident.endpoint_id == endpoint.id
    assert endpoint.path == "/api/v2/billing/invoices/42"
