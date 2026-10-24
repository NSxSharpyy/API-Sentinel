import asyncio

from app import queues
from app import main


def test_blocklist_verdict_queue_is_bounded():
    assert queues.blocklist_verdict_queue.maxsize == 1024


def test_blocklist_status_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(main.app.state, "blocklist_sync_enabled", False, raising=False)
    monkeypatch.setattr(main.app.state, "blocklist_synchronizer", None, raising=False)
    monkeypatch.setattr(main.app.state, "blocklist_sync_task", None, raising=False)

    result = asyncio.run(main.blocklist_status())

    assert result["status"] == "disabled"
    assert result["enabled"] is False
    assert result["queue_capacity"] == 1024
    assert result["kernel_map_pin"] == (
        "/sys/fs/bpf/api_sentinel_day17_blocklist"
    )
    assert result["packet_drop_enforcement_configured"] is False


def test_blocklist_status_includes_worker_metrics(monkeypatch):
    class FakeSynchronizer:
        def snapshot(self):
            return {
                "received_count": 3,
                "applied_count": 2,
                "rejected_count": 1,
                "failed_count": 0,
                "queue_depth": 0,
            }

    class FakeProducer:
        def snapshot(self):
            return {
                "producer_enabled": True,
                "submitted_count": 7,
                "rejected_count": 4,
                "disabled_count": 2,
                "queue_full_count": 1,
                "submission_queue_depth": 0,
                "submission_queue_capacity": 1024,
            }

    class RunningTask:
        def done(self):
            return False

    monkeypatch.setattr(main.app.state, "blocklist_sync_enabled", True, raising=False)
    monkeypatch.setattr(
        main.app.state, "blocklist_synchronizer", FakeSynchronizer(), raising=False
    )
    monkeypatch.setattr(main.app.state, "blocklist_sync_task", RunningTask(), raising=False)
    monkeypatch.setattr(
        main.app.state, "blocklist_verdict_producer", FakeProducer(), raising=False
    )

    result = asyncio.run(main.blocklist_status())

    assert result["status"] == "running"
    assert result["enabled"] is True
    assert result["applied_count"] == 2
    assert result["rejected_count"] == 1
    assert result["producer_submitted_count"] == 7
    assert result["producer_rejected_count"] == 4
    assert result["producer_queue_full_count"] == 1
    assert result["packet_drop_enforcement_configured"] is False


def test_blocklist_status_http_route_defaults_to_disabled(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        main.app.state, "blocklist_sync_enabled", False, raising=False
    )
    monkeypatch.setattr(
        main.app.state, "blocklist_synchronizer", None, raising=False
    )
    monkeypatch.setattr(
        main.app.state, "blocklist_sync_task", None, raising=False
    )
    monkeypatch.setattr(
        main.app.state, "blocklist_verdict_producer", None, raising=False
    )

    # Intentionally do not use the context manager: this tests the route
    # without starting capture services or the application lifespan.
    client = TestClient(main.app)
    response = client.get("/blocklist-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "disabled"
    assert payload["enabled"] is False
    assert payload["producer_enabled"] is False
    assert payload["producer_submitted_count"] == 0
    assert payload["producer_rejected_count"] == 0
    assert payload["packet_drop_enforcement_configured"] is False
