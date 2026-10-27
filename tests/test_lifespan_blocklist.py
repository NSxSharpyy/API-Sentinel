import asyncio
from types import SimpleNamespace

import pytest

from app import blocklist_map_writer, blocklist_policy, blocklist_sync
from app import blocklist_verdict_client, blocklist_verdict_receiver, main


class FakePublisher:
    def __init__(self, *args, **kwargs):
        self.closed = False

    def close(self):
        self.closed = True


class FakeStore:
    def __init__(self, alert_bus=None):
        self.alert_bus = alert_bus
        self.blocklist_policy = None
        self.bola_detector = object()


class FakePersistenceWorker:
    def __init__(self, store):
        self.store = store
        self.queue = asyncio.Queue(maxsize=16)
        self.persisted_count = 0
        self.failed_count = 0
        self.rejected_count = 0

    async def run(self, stop_event):
        await stop_event.wait()


class FakeWriter:
    instances = []

    def __init__(self, *args, **kwargs):
        self.closed = False
        self.__class__.instances.append(self)

    def close(self):
        self.closed = True


class FakeSynchronizer:
    instances = []

    def __init__(self, verdict_queue, map_writer, **kwargs):
        self.verdict_queue = verdict_queue
        self.map_writer = map_writer
        self.closed = False
        self.__class__.instances.append(self)

    async def run(self, stop_event):
        await stop_event.wait()


class FakeReceiver:
    instances = []

    def __init__(self, producer, *args, **kwargs):
        self.producer = producer
        self.endpoint = kwargs.get("endpoint", "tcp://127.0.0.1:5558")
        self.closed = False
        self.__class__.instances.append(self)

    async def run(self, stop_event):
        await stop_event.wait()

    def snapshot(self):
        return {"receiver_messages_accepted": 0}

    def close(self):
        self.closed = True


class FakeSenderOwner:
    instances = []

    def __init__(self, sender_factory):
        self.sender_factory = sender_factory
        self.closed = False
        self.__class__.instances.append(self)

    def send(self, payload):
        raise AssertionError("This lifecycle test must not send a verdict")

    def close(self):
        self.closed = True


async def _wait_for_stop(_pipeline, stop_event):
    await stop_event.wait()


async def _fake_supervise_capture(command, stop_event, on_status=None):
    if on_status is not None:
        on_status("running")
    await stop_event.wait()


async def _noop_initialize_async_database():
    return None


def _patch_common(monkeypatch):
    monkeypatch.setattr(
        main, "initialize_async_database", _noop_initialize_async_database
    )
    monkeypatch.setattr(main, "HTTPTransactionPublisher", FakePublisher)
    monkeypatch.setattr(main, "AsyncTransactionStore", FakeStore)
    monkeypatch.setattr(main, "TransactionPersistenceWorker", FakePersistenceWorker)
    monkeypatch.setattr(main, "packet_worker", _wait_for_stop)
    monkeypatch.setattr(main, "supervise_capture", _fake_supervise_capture)


def _clear_flags(monkeypatch):
    monkeypatch.delenv("API_SENTINEL_BLOCKLIST_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("API_SENTINEL_BLOCKLIST_POLICY_ENABLED", raising=False)
    monkeypatch.delenv("API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS", raising=False)


def test_lifespan_fails_closed_when_policy_enabled_without_sync(monkeypatch):
    _patch_common(monkeypatch)
    _clear_flags(monkeypatch)
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_POLICY_ENABLED", "1")
    test_app = SimpleNamespace(state=SimpleNamespace())

    async def scenario():
        with pytest.raises(RuntimeError, match="requires API_SENTINEL_BLOCKLIST_SYNC_ENABLED"):
            async with main.lifespan(test_app):
                pass

    asyncio.run(scenario())


def test_lifespan_fails_closed_when_allowlist_is_missing(monkeypatch):
    _patch_common(monkeypatch)
    _clear_flags(monkeypatch)
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_SYNC_ENABLED", "1")
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_POLICY_ENABLED", "1")
    test_app = SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr(blocklist_map_writer, "LibbpfBlocklistMapWriter", FakeWriter)
    monkeypatch.setattr(blocklist_sync, "BlocklistSynchronizer", FakeSynchronizer)
    monkeypatch.setattr(blocklist_verdict_receiver, "BlocklistVerdictReceiver", FakeReceiver)
    monkeypatch.setattr(blocklist_policy, "ThreadOwnedVerdictSender", FakeSenderOwner)
    monkeypatch.setattr(blocklist_verdict_client, "BlocklistVerdictSender", lambda: object())

    async def scenario():
        with pytest.raises(ValueError, match="requires an exact allowlist"):
            async with main.lifespan(test_app):
                pass

    asyncio.run(scenario())


def test_lifespan_starts_and_stops_opted_in_blocklist_services(monkeypatch):
    _patch_common(monkeypatch)
    _clear_flags(monkeypatch)
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_SYNC_ENABLED", "1")
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_POLICY_ENABLED", "1")
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS", "198.18.0.2")
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_VERDICT_TTL_SECONDS", "20")
    configured_endpoint = "tcp://127.0.0.1:45558"
    monkeypatch.setenv("API_SENTINEL_BLOCKLIST_VERDICT_ENDPOINT", configured_endpoint)
    monkeypatch.setattr(blocklist_map_writer, "LibbpfBlocklistMapWriter", FakeWriter)
    monkeypatch.setattr(blocklist_sync, "BlocklistSynchronizer", FakeSynchronizer)
    monkeypatch.setattr(blocklist_verdict_receiver, "BlocklistVerdictReceiver", FakeReceiver)
    monkeypatch.setattr(blocklist_policy, "ThreadOwnedVerdictSender", FakeSenderOwner)
    monkeypatch.setattr(
        blocklist_verdict_client,
        "BlocklistVerdictSender",
        lambda endpoint="tcp://127.0.0.1:5558": {"endpoint": endpoint},
    )
    test_app = SimpleNamespace(state=SimpleNamespace())

    async def scenario():
        async with main.lifespan(test_app):
            assert test_app.state.blocklist_sync_enabled is True
            assert test_app.state.blocklist_policy.enabled is True
            assert test_app.state.blocklist_policy.snapshot()["ttl_seconds"] == 20
            assert not test_app.state.blocklist_sync_task.done()
            assert not test_app.state.blocklist_verdict_receiver_task.done()
            assert test_app.state.blocklist_synchronizer is FakeSynchronizer.instances[-1]
            assert test_app.state.blocklist_verdict_receiver is FakeReceiver.instances[-1]
            assert test_app.state.blocklist_verdict_receiver.endpoint == configured_endpoint
            assert FakeSenderOwner.instances[-1].sender_factory()["endpoint"] == configured_endpoint

    asyncio.run(scenario())
    assert FakeWriter.instances[-1].closed is True
    assert FakeReceiver.instances[-1].closed is True
    assert FakeSenderOwner.instances[-1].closed is True
