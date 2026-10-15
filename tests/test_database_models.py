import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    DiscoveredEndpoint,
    SecurityIncident,
    TransactionLog,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        yield db

    engine.dispose()


def test_create_endpoint_transaction_and_incident(session):
    endpoint = DiscoveredEndpoint(
        host="example.test",
        method="GET",
        path="/api/users?page=1",
    )
    session.add(endpoint)
    session.flush()

    transaction = TransactionLog(
        endpoint_id=endpoint.id,
        source_ip="192.0.2.10",
        destination_ip="192.0.2.20",
        request_method="GET",
        request_uri="/api/users?page=1",
        response_status=200,
        request_headers={"host": "example.test"},
    )
    session.add(transaction)
    session.flush()

    incident = SecurityIncident(
        endpoint_id=endpoint.id,
        transaction_id=transaction.id,
        severity="high",
        title="Suspicious request",
        source_ip="192.0.2.10",
    )
    session.add(incident)
    session.commit()

    saved_endpoint = session.scalar(
        select(DiscoveredEndpoint).where(
            DiscoveredEndpoint.host == "example.test"
        )
    )

    assert saved_endpoint is not None
    assert saved_endpoint.transactions[0].response_status == 200
    assert saved_endpoint.incidents[0].severity == "high"
    assert saved_endpoint.transactions[0].request_headers["host"] == (
        "example.test"
    )


def test_duplicate_endpoint_is_rejected(session):
    endpoint = DiscoveredEndpoint(
        host="example.test", method="GET", path="/health"
    )
    session.add(endpoint)
    session.commit()

    session.add(
        DiscoveredEndpoint(
            host="example.test", method="GET", path="/health"
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_incident_can_exist_without_transaction(session):
    incident = SecurityIncident(
        severity="medium",
        title="Uncorrelated detection",
    )
    session.add(incident)
    session.commit()

    assert incident.id is not None
    assert incident.transaction_id is None
