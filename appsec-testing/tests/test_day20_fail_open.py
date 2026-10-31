"""Regression tests for the Day 20 simulated fail-open HTTP wrapper."""

import sys
from pathlib import Path
from unittest.mock import Mock

import requests

# Ensure the appsec-testing project root is importable under pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.enforcement import fail_open_wrapper as wrapper


def make_upstream_response(status=200, body=b'{"status":"ok"}'):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = "application/json"
    return response


def test_healthy_enforcer_routes_through_enforcer(monkeypatch):
    monkeypatch.setattr(wrapper, "enforcer_is_healthy", lambda: True)
    upstream = make_upstream_response()
    upstream.headers["X-Day20-Test-Enforcer"] = "active"
    request_mock = Mock(return_value=upstream)
    monkeypatch.setattr(wrapper.requests, "request", request_mock)

    client = wrapper.app.test_client()
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Enforcement-Active"] == "true"
    assert response.headers["X-Fail-Open-Mode"] == "enforced"
    assert response.headers["X-Day20-Test-Enforcer"] == "active"
    assert request_mock.call_args.kwargs["url"] == (
        f"{wrapper.ENFORCER_URL}/health"
    )


def test_unhealthy_enforcer_routes_directly_to_billing(monkeypatch):
    monkeypatch.setattr(wrapper, "enforcer_is_healthy", lambda: False)
    upstream = make_upstream_response()
    request_mock = Mock(return_value=upstream)
    monkeypatch.setattr(wrapper.requests, "request", request_mock)

    client = wrapper.app.test_client()
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Enforcement-Active"] == "false"
    assert response.headers["X-Fail-Open-Mode"] == "bypass"
    assert "X-Day20-Test-Enforcer" not in response.headers
    assert request_mock.call_args.kwargs["url"] == (
        f"{wrapper.DIRECT_UPSTREAM_URL}/health"
    )


def test_query_string_is_preserved_during_bypass(monkeypatch):
    monkeypatch.setattr(wrapper, "enforcer_is_healthy", lambda: False)
    request_mock = Mock(return_value=make_upstream_response())
    monkeypatch.setattr(wrapper.requests, "request", request_mock)

    client = wrapper.app.test_client()
    response = client.get("/health?source=day20&check=1")

    assert response.status_code == 200
    assert request_mock.call_args.kwargs["url"] == (
        f"{wrapper.DIRECT_UPSTREAM_URL}/health?source=day20&check=1"
    )


def test_enforcer_request_failure_does_not_silently_bypass(monkeypatch):
    monkeypatch.setattr(wrapper, "enforcer_is_healthy", lambda: True)

    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("simulated enforcer request failure")

    monkeypatch.setattr(
        wrapper.requests, "request", raise_connection_error
    )

    client = wrapper.app.test_client()
    response = client.get("/health")

    assert response.status_code == 502
    assert response.get_json()["error"] == "upstream_unavailable"


def test_wrapper_health_reports_fail_open_mode(monkeypatch):
    monkeypatch.setattr(wrapper, "enforcer_is_healthy", lambda: False)

    client = wrapper.app.test_client()
    response = client.get("/__wrapper_health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "enforcer_healthy": False,
        "routing_mode": "fail_open",
    }
