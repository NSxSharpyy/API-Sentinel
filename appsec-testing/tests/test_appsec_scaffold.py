"""Day 1 scaffold tests updated for Day 2 services."""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

STUBS = {
    "auth_service": ("POST", "/api/v2/auth/login", 400),
    "user_service": ("GET", "/api/v2/users/me", 401),
    "order_service": ("GET", "/api/v2/orders", 401),
    "billing_service": ("GET", "/api/v2/billing/invoices/1", 401),
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
    return request.param, load_app(request.param).test_client()


def test_health_ok(service):
    _, client = service
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_unauthenticated_first_route_is_rejected(service):
    name, client = service
    method, path, expected = STUBS[name]
    response = client.open(path, method=method)
    assert response.status_code == expected
    assert response.status_code != 501


def test_unknown_route_is_json_404_without_leaks(service):
    _, client = service
    response = client.get("/api/v2/does-not-exist")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not_found"}
    assert "Traceback" not in response.get_data(as_text=True)


def test_wrong_method_is_json_405(service):
    _, client = service
    response = client.post("/health")
    assert response.status_code == 405
    assert response.get_json() == {"error": "method_not_allowed"}


def test_request_id_is_returned_and_echoed(service):
    _, client = service
    assert client.get("/health").headers.get("X-Request-ID")
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"
