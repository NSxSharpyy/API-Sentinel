import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import csv
import json

import pytest

from scripts.traffic.customer_pool import build_customer_pool
from scripts.traffic.traffic_generator import (
    LOG_FIELDS,
    TrafficGenerator,
    TrafficLogger,
)


def test_customer_pool_has_50_unique_customers():
    customers = build_customer_pool()

    assert len(customers) == 50
    assert len({customer.username for customer in customers}) == 50
    assert all(customer.password == "Password123!" for customer in customers)


def test_traffic_logger_writes_jsonl_and_csv(tmp_path):
    logger = TrafficLogger(tmp_path)
    record = {
        "timestamp": "2026-10-13T12:00:00+00:00",
        "request_id": "test-request-id",
	"legitimate": True,
        "username": "alice.anderson1",
        "action": "verify_token",
        "method": "GET",
        "path": "/api/v2/auth/verify",
        "status_code": 200,
        "latency_ms": 12.5,
    }

    try:
        logger.write(record)
        jsonl_path = logger.jsonl_path
        csv_path = logger.csv_path
    finally:
        logger.close()

    with jsonl_path.open(encoding="utf-8") as handle:
        assert json.loads(handle.readline()) == record

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert LOG_FIELDS == list(rows[0].keys())
    assert rows[0]["action"] == "verify_token"
    assert rows[0]["legitimate"] == "True"
    assert rows[0]["status_code"] == "200"


def test_invalid_delay_configuration_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        TrafficGenerator(
            output_dir=tmp_path,
            min_delay=2,
            max_delay=1,
        )


def test_zero_duration_is_rejected(tmp_path):
    generator = TrafficGenerator(output_dir=tmp_path)

    with pytest.raises(ValueError):
        generator.run(0)

    generator.session.close()
    generator.logger.close()


def test_customer_pool_rejects_empty_database(monkeypatch):
    from types import SimpleNamespace
    import scripts.traffic.customer_pool as customer_pool_module

    monkeypatch.setattr(
        customer_pool_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="[]", stderr=""),
    )

    with pytest.raises(RuntimeError, match="contains no customers"):
        build_customer_pool()


def test_concurrency_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="Concurrency"):
        TrafficGenerator(output_dir=tmp_path, concurrency=0)

    with pytest.raises(ValueError, match="Concurrency"):
        TrafficGenerator(output_dir=tmp_path, concurrency=-1)


def test_async_customer_cycles_keep_tokens_separate(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    generator = TrafficGenerator(output_dir=tmp_path, concurrency=2)
    observed = []

    async def fake_async_request(
        session, customer, method, path, action, token=None, **kwargs
    ):
        observed.append((customer.username, path, token))

        if path == "/api/v2/auth/login":
            return {
                "token": f"token-{customer.username}",
                "user_id": customer.user_id,
            }
        if path == "/api/v2/auth/verify":
            return {"valid": True}
        if path == "/api/v2/orders":
            return {"orders": []}
        if path == "/api/v2/billing/invoices":
            return {"invoices": []}
        return {"ok": True}

    monkeypatch.setattr(generator, "async_request", fake_async_request)

    customer_a = SimpleNamespace(
        username="customer-a", password="pass-a", user_id=1
    )
    customer_b = SimpleNamespace(
        username="customer-b", password="pass-b", user_id=2
    )

    async def run_cycles():
        await asyncio.gather(
            generator.async_customer_cycle(object(), customer_a),
            generator.async_customer_cycle(object(), customer_b),
        )

    try:
        asyncio.run(run_cycles())
        for username, path, token in observed:
            if path != "/api/v2/auth/login":
                assert token == f"token-{username}"
    finally:
        generator.session.close()
        generator.logger.close()


def test_async_request_adds_request_id_and_customer_logs(tmp_path):
    import asyncio
    from types import SimpleNamespace

    generator = TrafficGenerator(output_dir=tmp_path)

    class FakeResponse:
        status = 200
        content_type = "application/json"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        async def json(self):
            return {"valid": True}

    class FakeSession:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return FakeResponse()

    session = FakeSession()
    customer = SimpleNamespace(username="customer-test")

    try:
        result = asyncio.run(
            generator.async_request(
                session,
                customer,
                "GET",
                "/api/v2/auth/verify",
                "verify_token",
                token="test-token",
            )
        )

        assert result == {"valid": True}
        method, url, kwargs = session.calls[0]
        assert method == "GET"
        assert url.endswith(":5001/api/v2/auth/verify")
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert kwargs["headers"]["X-Request-ID"]

        with generator.logger.jsonl_path.open(encoding="utf-8") as handle:
            record = json.loads(handle.readline())

        assert record["username"] == "customer-test"
        assert record["request_id"] == kwargs["headers"]["X-Request-ID"]
        assert record["legitimate"] is True
        assert record["action"] == "verify_token"
        assert record["status_code"] == 200
    finally:
        generator.session.close()
        generator.logger.close()
