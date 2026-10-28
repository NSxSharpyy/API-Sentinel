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


def test_concurrent_requests_cannot_exceed_same_identity_limit(
    monkeypatch, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor

    configure_limiter(monkeypatch, tmp_path, limit=5, window=30)

    # Initialize the schema before concurrent requests begin.
    db = limiter.connect_db()
    db.close()

    identity = "concurrent-test-identity"
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(
            lambda _: limiter.check_and_record(identity, now=100.0),
            range(40),
        ))

    assert sum(allowed for allowed, _ in results) == 5
    assert all(
        retry_after == 0 if allowed else retry_after >= 0
        for allowed, retry_after in results
    )


def test_different_identities_have_independent_limits(
    monkeypatch, tmp_path
):
    configure_limiter(monkeypatch, tmp_path, limit=1, window=30)

    assert limiter.check_and_record("identity-a", now=100.0) == (True, 0)
    assert limiter.check_and_record("identity-a", now=100.0)[0] is False
    assert limiter.check_and_record("identity-b", now=100.0) == (True, 0)


def test_storage_failure_returns_503_without_forwarding(
    monkeypatch, tmp_path
):
    # A directory used as the database filename makes SQLite opening fail.
    configure_limiter(monkeypatch, tmp_path)
    monkeypatch.setattr(limiter, "DB_PATH", str(tmp_path))

    forwarded = []
    monkeypatch.setattr(
        limiter.requests,
        "request",
        lambda **kwargs: forwarded.append(kwargs),
    )

    response = limiter.app.test_client().get("/resource")

    assert response.status_code == 503
    assert response.get_json() == {"error": "rate_limiter_unavailable"}
    assert response.headers["Retry-After"] == "1"
    assert forwarded == []


def test_database_close_failure_returns_503_without_forwarding(
    monkeypatch,
):
    import sqlite3

    class CloseFailingDatabase:
        def execute(self, *args, **kwargs):
            # Simulate a successful transaction and an empty rate-limit window.
            class Result:
                def fetchall(self):
                    return []

            return Result()

        def commit(self):
            pass

        def close(self):
            raise sqlite3.OperationalError("simulated close failure")

    monkeypatch.setattr(
        limiter,
        "connect_db",
        lambda: CloseFailingDatabase(),
    )

    forwarded = []
    monkeypatch.setattr(
        limiter.requests,
        "request",
        lambda **kwargs: forwarded.append(kwargs),
    )

    response = limiter.app.test_client().get("/resource")

    assert response.status_code == 503
    assert response.get_json() == {"error": "rate_limiter_unavailable"}
    assert response.headers["Retry-After"] == "1"
    assert forwarded == []


def test_retry_after_matches_sliding_window_expiry(
    monkeypatch, tmp_path
):
    configure_limiter(monkeypatch, tmp_path, limit=1, window=5)
    monkeypatch.setattr(limiter.time, "time", lambda: 100.0)
    monkeypatch.setattr(
        limiter.requests,
        "request",
        lambda **kwargs: fake_upstream_response(),
    )

    client = limiter.app.test_client()
    assert client.get("/resource").status_code == 200

    blocked = client.get("/resource")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "5"
    assert blocked.get_json()["retry_after_seconds"] == 5


def test_sqlite_write_lock_becomes_storage_error(
    monkeypatch, tmp_path
):
    import sqlite3

    configure_limiter(monkeypatch, tmp_path)
    db_path = str(tmp_path / "state.sqlite3")

    # Create the schema before taking the lock.
    db = limiter.connect_db()
    db.close()

    blocker = sqlite3.connect(db_path, timeout=1)
    blocker.execute("BEGIN IMMEDIATE")

    # Use a short timeout so this regression test stays fast.
    monkeypatch.setattr(
        limiter,
        "connect_db",
        lambda: sqlite3.connect(db_path, timeout=0.05),
    )

    try:
        try:
            limiter.check_and_record("locked-identity", now=100.0)
        except limiter.RateLimitStorageError:
            pass
        else:
            raise AssertionError(
                "SQLite lock contention should raise RateLimitStorageError"
            )
    finally:
        blocker.rollback()
        blocker.close()


def test_active_recovery_requires_real_429_then_success(monkeypatch):
    from types import SimpleNamespace
    from scripts.rate_limiting import rate_limit_validation as validation

    responses = iter([
        SimpleNamespace(status_code=200),  # first request
        SimpleNamespace(status_code=429),  # limit reached
        SimpleNamespace(status_code=200),  # recovery after waiting
    ])
    sleeps = []
    monkeypatch.setattr(
        validation.requests, "get", lambda *a, **kw: next(responses)
    )
    monkeypatch.setattr(validation.time, "sleep", sleeps.append)
    monkeypatch.setattr(validation.secrets, "token_urlsafe", lambda n: "test-token")

    result = validation.run_recovery_check(
        "http://127.0.0.1:7001", "/", limit=1, window=5, timeout=1
    )

    assert result["pass"] is True
    assert result["observed_trigger_429"] is True
    assert result["post_window_status"] == 200
    assert sleeps == [5.1]
    assert len(result["identity_sha256"]) == 64
    assert all("test-token" not in str(r) for r in result["trigger_requests"])


def test_active_recovery_fails_without_observed_429(monkeypatch):
    from types import SimpleNamespace
    from scripts.rate_limiting import rate_limit_validation as validation

    monkeypatch.setattr(
        validation.requests, "get",
        lambda *a, **kw: SimpleNamespace(status_code=200),
    )
    sleeps = []
    monkeypatch.setattr(validation.time, "sleep", sleeps.append)
    monkeypatch.setattr(validation.secrets, "token_urlsafe", lambda n: "test-token")

    result = validation.run_recovery_check(
        "http://127.0.0.1:7001", "/", limit=1, window=5, timeout=1
    )

    assert result["pass"] is False
    assert result["observed_trigger_429"] is False
    assert result["post_window_status"] == 200
    assert sleeps == []


def test_negative_control_fails_on_429_or_transport_error(monkeypatch):
    from types import SimpleNamespace
    from scripts.rate_limiting import rate_limit_validation as validation

    responses = iter([
        SimpleNamespace(status_code=200),
        SimpleNamespace(status_code=429),
    ])
    monkeypatch.setattr(
        validation.requests, "get", lambda *a, **kw: next(responses)
    )
    monkeypatch.setattr(validation.secrets, "token_urlsafe", lambda n: "test-token")

    result = validation.run_negative_control(
        "http://127.0.0.1:7001", "/", limit=2,
        requested_count=2, timeout=1,
    )

    assert result["pass"] is False
    assert result["completed_requests"] == 2
    assert result["http_429"] == 1
    assert result["blocked_rate"] == 0.5
