from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


def _task(running):
    return SimpleNamespace(done=lambda: not running)


def test_healthz_reports_liveness():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_503_when_workers_are_not_ready(monkeypatch):
    monkeypatch.setattr(app.state, "capture_enabled", True, raising=False)
    monkeypatch.setattr(app.state, "capture_status", "stopped", raising=False)
    monkeypatch.setattr(app.state, "capture_task", None, raising=False)
    monkeypatch.setattr(app.state, "persistence_worker", None, raising=False)
    monkeypatch.setattr(
        app.state, "persistence_worker_task", None, raising=False
    )
    monkeypatch.setattr(app.state, "http_pipeline", None, raising=False)

    response = TestClient(app).get("/readyz")
    body = response.json()

    assert response.status_code == 503
    assert body["status"] == "not_ready"
    assert body["capture"]["enabled"] is True
    assert body["capture"]["running"] is False
    assert body["checks"]["capture_ready"] is False
    assert "raw_packet" in body["queue_depths"]
    assert "process_rss_bytes" in body["memory"]


def test_readyz_returns_200_when_core_workers_are_running(monkeypatch):
    persistence_queue = SimpleNamespace(qsize=lambda: 3, maxsize=20)
    worker = SimpleNamespace(queue=persistence_queue)

    monkeypatch.setattr(app.state, "capture_enabled", True, raising=False)
    monkeypatch.setattr(app.state, "capture_status", "running", raising=False)
    monkeypatch.setattr(
        app.state, "capture_task", _task(True), raising=False
    )
    monkeypatch.setattr(
        app.state, "persistence_worker", worker, raising=False
    )
    monkeypatch.setattr(
        app.state, "persistence_worker_task", _task(True), raising=False
    )
    monkeypatch.setattr(app.state, "http_pipeline", object(), raising=False)

    response = TestClient(app).get("/readyz")
    body = response.json()

    assert "tracemalloc_enabled" in body["memory"]
    assert "traced_current_bytes" in body["memory"]
    assert "traced_peak_bytes" in body["memory"]
    assert "tracemalloc_overhead_bytes" in body["memory"]
    assert response.status_code == 200
    assert body["status"] == "ready"
    assert body["capture"]["enabled"] is True
    assert body["capture"]["running"] is True
    assert all(body["checks"].values())
    assert body["queue_depths"]["persistence"] == {
        "depth": 3,
        "capacity": 20,
    }


def test_readyz_returns_200_when_capture_is_disabled(monkeypatch):
    persistence_queue = SimpleNamespace(qsize=lambda: 0, maxsize=20)
    worker = SimpleNamespace(queue=persistence_queue)

    monkeypatch.setattr(app.state, "capture_enabled", False, raising=False)
    monkeypatch.setattr(app.state, "capture_status", "disabled", raising=False)
    monkeypatch.setattr(app.state, "capture_task", None, raising=False)
    monkeypatch.setattr(
        app.state, "persistence_worker", worker, raising=False
    )
    monkeypatch.setattr(
        app.state, "persistence_worker_task", _task(True), raising=False
    )
    monkeypatch.setattr(app.state, "http_pipeline", object(), raising=False)

    response = TestClient(app).get("/readyz")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ready"
    assert body["capture"] == {
        "enabled": False,
        "running": False,
        "status": "disabled",
    }
    assert body["checks"]["capture_ready"] is True
    assert body["checks"]["persistence_worker_running"] is True
    assert body["checks"]["http_pipeline_initialized"] is True
    assert all(body["checks"].values())
