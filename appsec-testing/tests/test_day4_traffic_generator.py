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
