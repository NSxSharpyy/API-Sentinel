import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "deployment"
    / "deployment_orchestration_test.py"
)

SPEC = importlib.util.spec_from_file_location("day29_deployment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def completed(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def test_parse_timestamp_accepts_utc_z():
    parsed = MODULE.parse_timestamp("2026-11-02T10:00:00Z")

    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", ["", None, "0001-01-01T00:00:00Z"])
def test_parse_timestamp_rejects_empty_or_zero_values(value):
    with pytest.raises(ValueError):
        MODULE.parse_timestamp(value)


def test_verify_clean_state_passes_when_inventory_is_empty(monkeypatch):
    monkeypatch.setattr(
        MODULE,
        "project_inventory",
        lambda: {
            "containers": [],
            "volumes": [],
            "networks": [],
            "images": [],
        },
    )

    result = MODULE.verify_clean_state()

    assert all(not values for values in result.values())


def test_verify_clean_state_fails_if_project_resource_remains(monkeypatch):
    monkeypatch.setattr(
        MODULE,
        "project_inventory",
        lambda: {
            "containers": ["container-id"],
            "volumes": [],
            "networks": [],
            "images": [],
        },
    )

    with pytest.raises(RuntimeError, match="resources remain"):
        MODULE.verify_clean_state()


def test_inspect_deployment_timestamps_accepts_seed_before_apps(monkeypatch):
    seed_finished = "2026-11-02T10:00:05Z"
    app_started = "2026-11-02T10:00:06Z"

    payload = []
    for name, state in [
        ("api-sentinel-seed", {
            "Status": "exited",
            "ExitCode": 0,
            "FinishedAt": seed_finished,
        }),
        *[
            (f"api-sentinel-{service}", {"StartedAt": app_started})
            for service in ("auth", "user", "order", "billing")
        ],
    ]:
        payload.append({"Name": f"/{name}", "State": state})

    monkeypatch.setattr(
        MODULE,
        "run_command",
        lambda *args, **kwargs: completed(json.dumps(payload)),
    )

    result = MODULE.inspect_deployment_timestamps()

    assert result["seed_exit_code"] == 0
    assert set(result["application_start_order"]) == {
        "auth", "user", "order", "billing"
    }


def test_inspect_deployment_timestamps_rejects_seed_after_app(monkeypatch):
    payload = [
        {
            "Name": "/api-sentinel-seed",
            "State": {
                "Status": "exited",
                "ExitCode": 0,
                "FinishedAt": "2026-11-02T10:00:08Z",
            },
        },
        *[
            {
                "Name": f"/api-sentinel-{service}",
                "State": {"StartedAt": "2026-11-02T10:00:06Z"},
            }
            for service in ("auth", "user", "order", "billing")
        ],
    ]

    monkeypatch.setattr(
        MODULE,
        "run_command",
        lambda *args, **kwargs: completed(json.dumps(payload)),
    )

    with pytest.raises(RuntimeError, match="finished after"):
        MODULE.inspect_deployment_timestamps()


def test_inspect_deployment_timestamps_rejects_nonzero_seed_exit(monkeypatch):
    payload = [
        {
            "Name": "/api-sentinel-seed",
            "State": {
                "Status": "exited",
                "ExitCode": 1,
                "FinishedAt": "2026-11-02T10:00:05Z",
            },
        },
        *[
            {
                "Name": f"/api-sentinel-{service}",
                "State": {"StartedAt": "2026-11-02T10:00:06Z"},
            }
            for service in ("auth", "user", "order", "billing")
        ],
    ]

    monkeypatch.setattr(
        MODULE,
        "run_command",
        lambda *args, **kwargs: completed(json.dumps(payload)),
    )

    with pytest.raises(RuntimeError, match="did not exit successfully"):
        MODULE.inspect_deployment_timestamps()


def test_wait_for_health_accepts_all_four_services(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok"}

    monkeypatch.setattr(MODULE.requests, "get", lambda *a, **k: Response())

    result = MODULE.wait_for_health(timeout_seconds=2)

    assert set(result) == {"auth", "user", "order", "billing"}
    assert all(item["healthy"] for item in result.values())


def test_wait_for_health_rejects_unhealthy_service(monkeypatch):
    class Response:
        status_code = 503

        @staticmethod
        def json():
            return {"status": "unavailable"}

    monkeypatch.setattr(MODULE.requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(MODULE.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(MODULE.time, "sleep", lambda *_: None)

    with pytest.raises(RuntimeError, match="deadline expired"):
        MODULE.wait_for_health(timeout_seconds=0)


def test_end_to_end_smoke_test_checks_all_api_ownership(monkeypatch):
    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    responses = iter([
        Response(200, {
            "token": "test-token",
            "user_id": 1,
            "token_type": "Bearer",
        }),
        Response(200, {"valid": True, "user_id": 1}),
        Response(200, {"id": 1, "username": "alice.anderson1"}),
        Response(200, {"orders": [{"id": 1, "user_id": 1}]}),
        Response(200, {"invoices": [{"id": 1, "owner_id": 1}]}),
    ])

    calls = []

    def fake_request(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    monkeypatch.setattr(MODULE.requests, "post", fake_request)
    monkeypatch.setattr(MODULE.requests, "get", fake_request)

    result = MODULE.run_end_to_end_smoke_test()

    assert result["login"] == "PASS"
    assert result["token_verification"] == "PASS"
    assert result["profile"] == "PASS"
    assert result["orders_owner_check"] == "PASS"
    assert result["invoices_owner_check"] == "PASS"
    assert result["orders_count"] == 1
    assert result["invoices_count"] == 1
    assert len(calls) == 5


def test_end_to_end_smoke_test_rejects_cross_user_order(monkeypatch):
    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    responses = iter([
        Response(200, {
            "token": "test-token",
            "user_id": 1,
            "token_type": "Bearer",
        }),
        Response(200, {"valid": True, "user_id": 1}),
        Response(200, {"id": 1}),
        Response(200, {"orders": [{"id": 2, "user_id": 2}]}),
    ])

    def fake_request(*args, **kwargs):
        return next(responses)

    monkeypatch.setattr(MODULE.requests, "post", fake_request)
    monkeypatch.setattr(MODULE.requests, "get", fake_request)

    with pytest.raises(RuntimeError, match="another user"):
        MODULE.run_end_to_end_smoke_test()


def test_end_to_end_smoke_test_rejects_exposed_password_hash(monkeypatch):
    class Response:
        def __init__(self, body):
            self.status_code = 200
            self._body = body

        def json(self):
            return self._body

    responses = iter([
        Response({
            "token": "test-token",
            "user_id": 1,
            "token_type": "Bearer",
        }),
        Response({"valid": True, "user_id": 1}),
        Response({"id": 1, "password_hash": "must-not-be-exposed"}),
    ])

    def fake_request(*args, **kwargs):
        return next(responses)

    monkeypatch.setattr(MODULE.requests, "post", fake_request)
    monkeypatch.setattr(MODULE.requests, "get", fake_request)

    with pytest.raises(RuntimeError, match="password_hash"):
        MODULE.run_end_to_end_smoke_test()


def test_runner_requires_explicit_execute_flag(monkeypatch):
    monkeypatch.setattr(MODULE.sys, "argv", ["deployment_orchestration_test.py"])

    with pytest.raises(SystemExit) as exc:
        MODULE.main()

    assert exc.value.code == 2
