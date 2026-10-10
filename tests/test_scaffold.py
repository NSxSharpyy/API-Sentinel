"""Day 1 tests: every scaffolded service behaves safely and consistently."""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# One representative placeholder route per service
STUBS = {
    "auth_service": ("POST", "/api/v2/auth/login"),
    "user_service": ("GET", "/api/v2/users/me"),
    "order_service": ("GET", "/api/v2/orders"),
    "billing_service": ("GET", "/api/v2/billing/invoices/1"),
}


def load_app(service_dir):
    folder = ROOT / "services" / service_dir
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location(
            f"{service_dir}_app", folder / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        sys.path.remove(str(folder))


@pytest.fixture(params=list(STUBS))
def service(request):
    app = load_app(request.param)
    return request.param, app.test_client()


def test_health_ok(service):
    _, client = service
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_stub_route_returns_501(service):
    name, client = service
    method, path = STUBS[name]
    resp = client.open(path, method=method)
    assert resp.status_code == 501
    assert resp.get_json()["error"] == "not_implemented"


def test_unknown_route_is_json_404_without_leaks(service):
    _, client = service
    resp = client.get("/api/v2/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "not_found"}
    assert "Traceback" not in resp.get_data(as_text=True)


def test_wrong_method_is_json_405(service):
    _, client = service
    resp = client.post("/health")
    assert resp.status_code == 405
    assert resp.get_json() == {"error": "method_not_allowed"}


def test_request_id_is_returned_and_echoed(service):
    _, client = service
    assert client.get("/health").headers.get("X-Request-ID")
    resp = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert resp.headers["X-Request-ID"] == "trace-123"
