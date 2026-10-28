import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
import pytest

from app.database import Base
from app.async_transaction_store import AsyncTransactionStore
from app.http_reassembly import HTTPMessage
from app.models import DiscoveredEndpoint, SecurityIncident, TransactionLog
from app.transaction_correlator import HTTPTransaction


def make_transaction(
    method="GET",
    uri="/health",
    request_headers=None,
    response_body=b"OK",
):
    request = HTTPMessage(
        version="HTTP/1.1",
        headers=request_headers or {"host": "example.test"},
        body=b"",
        message_type="request",
        method=method,
        uri=uri,
        connection_id="TCP|10.0.0.10:49152->10.0.0.20:80",
    )
    response = HTTPMessage(
        version="HTTP/1.1",
        headers={"content-type": "application/json"},
        body=response_body,
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


async def make_store():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"autocommit": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )
    return engine, factory, AsyncTransactionStore(session_factory=factory)


def test_async_batch_persists_transactions_and_endpoint():
    async def scenario():
        engine, factory, store = await make_store()
        try:
            ids = await store.save_batch_async([
                make_transaction(),
                make_transaction(),
            ])
            assert len(ids) == 2

            assert store.batch_preparation_duration_count == 1
            assert store.batch_commit_duration_count == 1
            assert store.average_batch_preparation_duration_ms >= 0.0
            assert store.p95_batch_preparation_duration_ms >= 0.0
            assert store.max_batch_preparation_duration_ms >= 0.0
            assert store.average_batch_commit_duration_ms >= 0.0
            assert store.p95_batch_commit_duration_ms >= 0.0
            assert store.max_batch_commit_duration_ms >= 0.0

            assert ids[0] != ids[1]

            async with factory() as session:
                records = (
                    await session.scalars(
                        select(TransactionLog).order_by(TransactionLog.id)
                    )
                ).all()
                endpoints = (
                    await session.scalars(select(DiscoveredEndpoint))
                ).all()

            assert len(records) == 2
            assert len(endpoints) == 1
            assert all(r.endpoint_id == endpoints[0].id for r in records)
            assert endpoints[0].path == "/health"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_async_save_persists_bola_incident_atomically():
    async def scenario():
        engine, factory, store = await make_store()
        try:
            login = make_transaction(
                method="POST",
                uri="/api/v2/auth/login",
                request_headers={
                    "host": "billing.example.test",
                    "content-type": "application/json",
                },
                response_body=b'{"token":"lab-token","user_id":1}',
            )
            login.response.body = b'{"token":"lab-token","user_id":1}'
            await store.save_async(login)

            invoice = make_transaction(
                uri="/api/v2/billing/invoices/42",
                request_headers={
                    "host": "billing.example.test",
                    "authorization": "Bearer lab-token",
                },
                response_body=b'{"id":42,"owner_id":2,"status":"paid"}',
            )
            await store.save_async(invoice)

            async with factory() as session:
                incidents = (
                    await session.scalars(select(SecurityIncident))
                ).all()
                transactions = (
                    await session.scalars(select(TransactionLog))
                ).all()

            assert len(transactions) == 2
            assert len(incidents) == 1
            assert incidents[0].transaction_id == transactions[1].id
            assert incidents[0].endpoint_id == transactions[1].endpoint_id
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_async_save_rolls_back_when_commit_fails(monkeypatch):
    async def scenario():
        engine, factory, store = await make_store()
        try:
            async def fail_commit(self):
                raise RuntimeError("simulated async commit failure")

            monkeypatch.setattr(AsyncSession, "commit", fail_commit)

            with pytest.raises(RuntimeError, match="simulated async commit failure"):
                await store.save_async(make_transaction())

            async with factory() as session:
                records = (
                    await session.scalars(select(TransactionLog))
                ).all()
                endpoints = (
                    await session.scalars(select(DiscoveredEndpoint))
                ).all()

            assert records == []
            assert endpoints == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())

def test_async_batch_reuses_endpoint_upsert_and_keeps_latest_seen(monkeypatch):
    async def scenario():
        engine, factory, store = await make_store()
        try:
            first = make_transaction()
            second = make_transaction()

            first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            second_time = first_time + timedelta(seconds=30)
            first.request.captured_at = first_time
            second.request.captured_at = second_time

            original_upsert = store._upsert_endpoint
            upsert_calls = 0

            def counting_upsert(
                session, transaction, destination_ip, observed_at
            ):
                nonlocal upsert_calls
                upsert_calls += 1
                return original_upsert(
                    session, transaction, destination_ip, observed_at
                )

            monkeypatch.setattr(store, "_upsert_endpoint", counting_upsert)

            ids = await store.save_batch_async([first, second])
            assert len(ids) == 2
            assert upsert_calls == 1

            async with factory() as session:
                endpoints = (
                    await session.scalars(select(DiscoveredEndpoint))
                ).all()

            assert len(endpoints) == 1
            last_seen = endpoints[0].last_seen
            if last_seen.tzinfo is None or last_seen.utcoffset() is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            assert last_seen == second_time
        finally:
            await engine.dispose()

    asyncio.run(scenario())
