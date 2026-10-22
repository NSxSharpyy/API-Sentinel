import json

import requests

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from scripts.rate_limiting import mock_rate_limiter as limiter
from scripts.rate_limiting.rate_limit_validation import summarize


def configure_limiter(monkeypatch, tmp_path, limit=2, window=5):
    monkeypatch.setattr(limiter, "DB_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setattr(limiter, "LIMIT", limit)
    monkeypatch.setattr(limiter, "WINDOW", window)


def fake_upstream_response(status=200, body=b'{"ok":true}', headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers.update(headers or {"Content-Type": "application/json"})
    return response


def test_limit_returns_429_with_contract_body(monkeypatch, tmp_path):
    configure_limiter(monkeypatch, tmp_path, limit=2)
    monkeypatch.setattr(
        limiter.requests, "request",
        lambda **kwargs: fake_upstream_response(),
    )
    client = limiter.app.test_client()

    assert client.get("/resource").status_code == 200
    assert client.get("/resource").status_code == 200

    blocked = client.get("/resource")
    assert blocked.status_code == 429
    assert blocked.get_json()["error"] == "rate_limited"
    assert isinstance(blocked.get_json()["retry_after_seconds"], int)
    assert blocked.get_json()["retry_after_seconds"] >= 0
    assert blocked.headers["Retry-After"].isdigit()


def test_health_does_not_consume_rate_limit(monkeypatch, tmp_path):
    configure_limiter(monkeypatch, tmp_path, limit=1)
    monkeypatch.setattr(
        limiter.requests, "request",
        lambda **kwargs: fake_upstream_response(),
    )
    client = limiter.app.test_client()

    for _ in range(3):
        assert client.get("/health").status_code == 200

    assert client.get("/resource").status_code == 200
    assert client.get("/resource").status_code == 429


def test_upstream_connection_error_is_502_not_429(
    monkeypatch, tmp_path
):
    configure_limiter(monkeypatch, tmp_path, limit=20)

    def fail_upstream(**kwargs):
        raise requests.ConnectionError("test upstream failure")

    monkeypatch.setattr(limiter.requests, "request", fail_upstream)
    response = limiter.app.test_client().get("/resource")

    assert response.status_code == 502
    assert response.get_json() == {"error": "upstream_unavailable"}


def test_stale_content_encoding_is_not_forwarded(
    monkeypatch, tmp_path
):
    configure_limiter(monkeypatch, tmp_path, limit=20)
    upstream = fake_upstream_response(
        body=b'{"ok":true}',
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    monkeypatch.setattr(
        limiter.requests, "request",
        lambda **kwargs: upstream,
    )

    response = limiter.app.test_client().get("/resource")

    assert response.status_code == 200
    assert response.data == b'{"ok":true}'
    assert "Content-Encoding" not in response.headers


def test_sliding_window_allows_request_after_expiry(
    monkeypatch, tmp_path
):
    configure_limiter(monkeypatch, tmp_path, limit=1, window=5)
    clock = [100.0]
    monkeypatch.setattr(limiter.time, "time", lambda: clock[0])

    identity = "test-client"
    assert limiter.check_and_record(identity) == (True, 0)
    allowed, retry_after = limiter.check_and_record(identity)
    assert allowed is False
    assert retry_after >= 0

    clock[0] = 106.0
    assert limiter.check_and_record(identity) == (True, 0)


def test_bearer_identity_is_hashed(monkeypatch):
    with limiter.app.test_request_context(
        "/resource",
        headers={"Authorization": "Bearer test-secret-token"},
    ):
        identity = limiter.client_identity()

    assert identity != "test-secret-token"
    assert len(identity) == 64


def test_report_parser_separates_transport_errors(tmp_path):
    path = tmp_path / "run.jsonl"
    records = [
        {"status_code": 200},
        {"status_code": 429},
        {"status_code": 0, "error": "ConnectionError"},
    ]
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )

    report = summarize(path)

    assert report["records"] == 3
    assert report["completed_http_responses"] == 2
    assert report["transport_or_missing_status_errors"] == 1
    assert report["http_429"] == 1
    assert report["blocked_rate"] == 0.5
