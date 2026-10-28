"""Regression tests for the Day 20 simulated fail-closed proxy."""

import sys
from pathlib import Path
from unittest.mock import Mock

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.enforcement import day20_fail_closed_proxy as proxy


def make_upstream_response(status=200, body=b'{"status":"ok"}'):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = "application/json"
    return response


def test_healthy_enforcer_receives_forwarded_request(monkeypatch):
    monkeypatch.setattr(proxy, "enforcer_is_healthy", lambda: True)
    upstream = make_upstream_response()
    upstream.headers["X-Day20-Test-Enforcer"] = "active"

    request_mock = Mock(return_value=upstream)
    monkeypatch.setattr(proxy.requests, "request", request_mock)

    response = proxy.app.test_client().get("/health")

    assert response.status_code == 200
    assert response.headers["X-Fail-Closed-Mode"] == "enforced"
    assert response.headers["X-Enforcement-Active"] == "true"
    assert request_mock.call_args.kwargs["url"] == (
        f"{proxy.ENFORCER_URL}/health"
    )


def test_unhealthy_enforcer_is_rejected_without_forwarding(monkeypatch):
    monkeypatch.setattr(proxy, "enforcer_is_healthy", lambda: False)
    request_mock = Mock()
    monkeypatch.setattr(proxy.requests, "request", request_mock)

    response = proxy.app.test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json()["error"] == "enforcement_unavailable"
    assert response.headers["X-Fail-Closed-Mode"] == "reject"
    assert response.headers["X-Enforcement-Active"] == "false"
    request_mock.assert_not_called()


def test_enforcer_failure_after_health_check_still_fails_closed(monkeypatch):
    monkeypatch.setattr(proxy, "enforcer_is_healthy", lambda: True)

    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("simulated enforcer crash")

    request_mock = Mock(side_effect=raise_connection_error)
    monkeypatch.setattr(proxy.requests, "request", request_mock)

    response = proxy.app.test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json()["error"] == (
        "enforcement_upstream_unavailable"
    )
    assert response.headers["X-Fail-Closed-Mode"] == "reject"
    assert request_mock.call_args.kwargs["url"] == (
        f"{proxy.ENFORCER_URL}/health"
    )


def test_query_string_is_preserved(monkeypatch):
    monkeypatch.setattr(proxy, "enforcer_is_healthy", lambda: True)
    request_mock = Mock(return_value=make_upstream_response())
    monkeypatch.setattr(proxy.requests, "request", request_mock)

    response = proxy.app.test_client().get(
        "/health?source=day20&check=1"
    )

    assert response.status_code == 200
    assert request_mock.call_args.kwargs["url"] == (
        f"{proxy.ENFORCER_URL}/health?source=day20&check=1"
    )


def test_proxy_health_is_independent_of_enforcer(monkeypatch):
    monkeypatch.setattr(proxy, "enforcer_is_healthy", lambda: False)

    response = proxy.app.test_client().get("/__fail_closed_proxy_health")

    assert response.status_code == 200
    assert response.get_json()["mode"] == "fail-closed"
