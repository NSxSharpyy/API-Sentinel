from collections import deque
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import queues
from app.main import app


def test_debug_http_parsers_exposes_aggregate_diagnostics_only(monkeypatch):
    connection_id = "TCP|10.1.2.3:49152->10.4.5.6:443"
    sensitive_path = "/users/private-user-123/profile"
    parser = SimpleNamespace(
        buffer=f"GET {sensitive_path} HTTP/1.1\r\n".encode(),
        pending_head_responses=1,
    )
    correlator = SimpleNamespace(
        pending_request_count=2,
        unmatched_responses=3,
        dropped_requests=4,
        expired_requests=1,
        capacity_evicted_requests=1,
        connection_closed_requests=2,
        drop_reason_counts={"tcp_rst": 2},
        recent_drop_samples=deque(
            [{"reason": "tcp_rst", "method": "GET", "age_seconds": 0.1}],
            maxlen=100,
        ),
    )
    pipeline = SimpleNamespace(
        _parsers={connection_id: parser},
        parsed_request_count=5,
        parsed_response_count=6,
        transaction_processing_count=3,
        completed_transactions=deque([object()], maxlen=1000),
        correlator=correlator,
    )
    monkeypatch.setattr(app.state, "http_pipeline", pipeline, raising=False)
    monkeypatch.setattr(
        queues,
        "tcp_stream_diagnostics",
        {
            "active_streams": 1,
            "reported_streams": 1,
            "streams": [
                {
                    "connection_id": connection_id,
                    "next_expected_sequence": 123456,
                    "buffered_bytes": 32,
                    "pending_sequence_numbers": [123450],
                    "last_seen_monotonic": 100.0,
                }
            ],
        },
        raising=False,
    )

    response = TestClient(app).get("/debug/http-parsers")

    assert response.status_code == 200
    body = response.json()
    assert body["parser_count"] == 1
    assert body["buffered_parser_count"] == 1
    assert body["total_buffered_bytes"] == len(parser.buffer)
    assert body["pending_head_responses"] == 1
    assert body["active_tcp_streams"] == 1
    assert body["drop_reason_counts"] == {"tcp_rst": 2}

    serialized = response.text
    for sensitive_value in (
        connection_id,
        sensitive_path,
        "next_expected_sequence",
        "pending_sequence_numbers",
        "recent_dropped_request_samples",
        "tcp_stream_diagnostics",
    ):
        assert sensitive_value not in serialized
