import json
import pytest
import app.message_broker as broker
from app.http_reassembly import HTTPMessage
from app.serialization_metrics import SerializationLatencyMetrics
from app.transaction_correlator import HTTPTransaction


def make_request():
    return HTTPMessage(
        method="GET",
        uri="/metrics-test",
        version="HTTP/1.1",
        headers={"host": "example.test"},
        body=b"",
        message_type="request",
        connection_id="TCP|192.0.2.10:49152->192.0.2.20:80",
    )


def make_response():
    return HTTPMessage(
        version="HTTP/1.1",
        headers={},
        body=b"OK",
        message_type="response",
        status_code=200,
        reason_phrase="OK",
        connection_id="TCP|192.0.2.20:80->192.0.2.10:49152",
    )


def test_serialization_metrics_are_bounded_and_report_percentiles():
    metrics = SerializationLatencyMetrics(sample_capacity=3)
    for elapsed_ns in (500_000, 900_000, 1_200_000, 2_000_000):
        metrics.record(elapsed_ns)

    result = metrics.snapshot()
    assert result["count"] == 4
    assert result["sample_count"] == 3
    assert result["under_1ms_sample_count"] == 1
    assert result["under_1ms_sample_percent"] == pytest.approx(100 / 3)
    assert result["p50_latency_us"] == 1200.0
    assert result["p95_latency_us"] == 2000.0


def test_http_message_serialization_records_duration(monkeypatch):
    metrics = SerializationLatencyMetrics()
    monkeypatch.setattr(
        broker, "http_message_serialization_metrics", metrics
    )

    payload = broker.serialize_http_message(make_request())

    assert json.loads(payload)["uri"] == "/metrics-test"
    result = metrics.snapshot()
    assert result["count"] == 1
    assert result["sample_count"] == 1
    assert result["last_latency_us"] >= 0


def test_http_transaction_serialization_records_duration(monkeypatch):
    metrics = SerializationLatencyMetrics()
    monkeypatch.setattr(
        broker, "http_transaction_serialization_metrics", metrics
    )

    transaction = HTTPTransaction(
        connection_key="TCP|192.0.2.10:49152<->192.0.2.20:80",
        request=make_request(),
        response=make_response(),
    )
    payload = broker.serialize_http_transaction(transaction)

    event = json.loads(payload)
    assert event["message_type"] == "completed_transaction"
    assert event["request"]["uri"] == "/metrics-test"
    result = metrics.snapshot()
    assert result["count"] == 1
    assert result["sample_count"] == 1
    assert result["last_latency_us"] >= 0
