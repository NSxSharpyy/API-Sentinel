import asyncio
import json
import sys
import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.blocklist_drop_audit import (
    AsyncBlockedTransactionAuditStore,
    supervise_blocklist_drop_audit,
)
from app.database import Base
from app.models import BlockedTransactionAudit


def sample_event():
    return {
        "source_ip": "192.0.2.10",
        "destination_ip": "10.0.0.20",
        "source_port": 49152,
        "destination_port": 443,
        "protocol": "TCP",
        "rule_id": "day21-async-audit-test",
        "interface_index": 1,
        "captured_at_ns": time.monotonic_ns() - 1_000_000,
    }


def test_async_audit_store_persists_validated_drop_event():
    async def scenario():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"autocommit": False},
            poolclass=StaticPool,
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            factory = async_sessionmaker(
                engine, expire_on_commit=False, autoflush=False
            )
            store = AsyncBlockedTransactionAuditStore(factory)
            audit_id = await store.record_drop_async(sample_event())

            async with factory() as session:
                record = await session.get(BlockedTransactionAudit, audit_id)

            assert record is not None
            assert record.attacker_ip == "192.0.2.10"
            assert record.target_ip == "10.0.0.20"
            assert record.target_endpoint == "10.0.0.20:443"
            assert record.protocol == "TCP"
            assert record.rule_id == "day21-async-audit-test"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_async_audit_store_rejects_invalid_event_before_database_write():
    async def scenario():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"autocommit": False},
            poolclass=StaticPool,
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            factory = async_sessionmaker(
                engine, expire_on_commit=False, autoflush=False
            )
            store = AsyncBlockedTransactionAuditStore(factory)
            event = sample_event()
            event["destination_ip"] = "not-an-ip"

            with pytest.raises(ValueError, match="invalid IP address"):
                await store.record_drop_async(event)

            async with factory() as session:
                records = (
                    await session.scalars(select(BlockedTransactionAudit))
                ).all()
            assert records == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_audit_supervisor_awaits_async_writer():
    async def scenario():
        event = sample_event()
        stop_event = asyncio.Event()
        recorded = asyncio.Event()
        received = []

        class AsyncSink:
            async def record_drop_async(self, item):
                received.append(item)
                recorded.set()

            def record_drop(self, item):
                raise AssertionError("async writer should be preferred")

        script = "import json; print(json.dumps(" + repr(event) + "), flush=True)"
        task = asyncio.create_task(
            supervise_blocklist_drop_audit(
                [sys.executable, "-c", script],
                stop_event,
                AsyncSink(),
                restart_delay=0.05,
            )
        )
        try:
            await asyncio.wait_for(recorded.wait(), timeout=3)
        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=3)

        assert received == [event]

    asyncio.run(scenario())
