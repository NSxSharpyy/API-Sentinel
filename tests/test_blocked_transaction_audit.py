import asyncio
import json
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.blocklist_drop_audit import (
    BlockedTransactionAuditStore,
    supervise_blocklist_drop_audit,
)
from app.database import Base
from app.models import BlockedTransactionAudit


@pytest.fixture
def audit_sessions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    yield sessions
    engine.dispose()


def sample_event(**overrides):
    event = {
        "captured_at_ns": time.monotonic_ns(),
        "interface_index": 2,
        "source_ip": "192.0.2.10",
        "destination_ip": "192.0.2.20",
        "source_port": 51234,
        "destination_port": 443,
        "protocol": "TCP",
        "rule_id": "day17.ipv4_source_blocklist",
    }
    event.update(overrides)
    return event


def test_drop_event_is_persisted_with_required_audit_fields(audit_sessions):
    store = BlockedTransactionAuditStore(audit_sessions)

    audit_id = store.record_drop(sample_event())

    with audit_sessions() as session:
        row = session.scalar(
            select(BlockedTransactionAudit).where(
                BlockedTransactionAudit.id == audit_id
            )
        )

    assert row is not None
    assert row.attacker_identifier == "192.0.2.10"
    assert row.attacker_ip == "192.0.2.10"
    assert row.target_endpoint == "192.0.2.20:443"
    assert row.target_ip == "192.0.2.20"
    assert row.source_port == 51234
    assert row.target_port == 443
    assert row.protocol == "TCP"
    assert row.rule_id == "day17.ipv4_source_blocklist"
    assert row.interface_index == 2
    assert row.dropped_at is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_ip": "not-an-ip"},
        {"destination_ip": "2001:db8::1"},
        {"source_port": -1},
        {"destination_port": 65536},
        {"protocol": "ICMP-FAKE"},
        {"rule_id": ""},
        {"interface_index": 0},
        {"captured_at_ns": True},
    ],
)
def test_invalid_drop_event_is_rejected(audit_sessions, overrides):
    store = BlockedTransactionAuditStore(audit_sessions)

    with pytest.raises(ValueError):
        store.record_drop(sample_event(**overrides))

    with audit_sessions() as session:
        assert session.scalar(select(BlockedTransactionAudit)) is None


def test_non_tcp_udp_drop_records_endpoint_ip_without_port(audit_sessions):
    store = BlockedTransactionAuditStore(audit_sessions)

    audit_id = store.record_drop(
        sample_event(protocol="OTHER", destination_port=0, source_port=0)
    )

    with audit_sessions() as session:
        row = session.get(BlockedTransactionAudit, audit_id)

    assert row is not None
    assert row.target_endpoint == "192.0.2.20"
    assert row.protocol == "OTHER"


def test_supervisor_persists_json_reader_event_and_stops(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'drop-audit-integration.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    persisted = threading.Event()

    class NotifyingAuditStore(BlockedTransactionAuditStore):
        def record_drop(self, event):
            audit_id = super().record_drop(event)
            persisted.set()
            return audit_id

    store = NotifyingAuditStore(sessions)
    event = sample_event()
    child_script = (
        "import json,time; "
        f"print(json.dumps({event!r}), flush=True); "
        "time.sleep(30)"
    )

    async def scenario():
        stop_event = asyncio.Event()
        task = asyncio.create_task(
            supervise_blocklist_drop_audit(
                [sys.executable, "-u", "-c", child_script],
                stop_event,
                store,
                restart_delay=0.1,
            )
        )
        try:
            assert await asyncio.to_thread(persisted.wait, 3), (
                "JSON event was not persisted by the supervised reader"
            )
        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=3)

    try:
        asyncio.run(scenario())
        with sessions() as session:
            rows = list(session.scalars(select(BlockedTransactionAudit)).all())

        assert len(rows) == 1
        assert rows[0].attacker_ip == "192.0.2.10"
        assert rows[0].target_endpoint == "192.0.2.20:443"
        assert rows[0].rule_id == "day17.ipv4_source_blocklist"
    finally:
        engine.dispose()
