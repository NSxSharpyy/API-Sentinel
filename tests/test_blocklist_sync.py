import asyncio
import time

import pytest

from app.blocklist_sync import (
    BlockVerdict,
    BlocklistSynchronizer,
    VerdictValidationError,
)


class RecordingWriter:
    def __init__(self):
        self.applied = []

    def apply(self, verdict):
        self.applied.append(verdict)


def make_payload(**overrides):
    payload = {
        "verdict_id": "verdict-001",
        "action": "block",
        "source_ip": "198.51.100.25",
        "rule_id": "test-rule-1",
        "issued_at_ns": time.time_ns(),
    }
    payload.update(overrides)
    return payload


def test_parse_valid_block_verdict():
    verdict = BlockVerdict.from_payload(make_payload())

    assert str(verdict.source_ip) == "198.51.100.25"
    assert verdict.action == "block"
    assert verdict.rule_id == "test-rule-1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "drop-everything"},
        {"source_ip": "127.0.0.1"},
        {"source_ip": "0.0.0.0"},
        {"source_ip": "224.0.0.1"},
        {"source_ip": "2001:db8::1"},
        {"issued_at_ns": True},
        {"rule_id": ""},
    ],
)
def test_reject_invalid_verdict(overrides):
    with pytest.raises(VerdictValidationError):
        BlockVerdict.from_payload(make_payload(**overrides))


def test_reject_expired_verdict():
    now = time.time_ns()
    payload = make_payload(
        issued_at_ns=now - 2_000_000_000,
        expires_at_ns=now - 1_000_000_000,
    )

    with pytest.raises(VerdictValidationError, match="expired"):
        BlockVerdict.from_payload(payload)


def test_worker_applies_once_and_rejects_unsafe_address():
    async def scenario():
        queue = asyncio.Queue()
        writer = RecordingWriter()
        worker = BlocklistSynchronizer(queue, writer)
        stop_event = asyncio.Event()
        task = asyncio.create_task(worker.run(stop_event))

        valid = make_payload()
        queue.put_nowait(valid)
        queue.put_nowait(valid)  # Duplicate verdict ID.
        queue.put_nowait(
            make_payload(
                verdict_id="unsafe-001",
                source_ip="127.0.0.1",
            )
        )

        await asyncio.wait_for(queue.join(), timeout=2)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2)

        return writer, worker.snapshot()

    writer, metrics = asyncio.run(scenario())

    assert len(writer.applied) == 1
    assert metrics["received_count"] == 3
    assert metrics["applied_count"] == 1
    assert metrics["duplicate_count"] == 1
    assert metrics["rejected_count"] == 1
    assert metrics["failed_count"] == 0
    assert metrics["queue_depth"] == 0


def test_writer_failure_is_counted_without_crashing_worker():
    class FailingWriter:
        def apply(self, verdict):
            raise OSError("simulated map write failure")

    async def scenario():
        queue = asyncio.Queue()
        worker = BlocklistSynchronizer(queue, FailingWriter())
        stop_event = asyncio.Event()
        task = asyncio.create_task(worker.run(stop_event))
        queue.put_nowait(make_payload())

        await asyncio.wait_for(queue.join(), timeout=2)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2)
        return worker.snapshot()

    metrics = asyncio.run(scenario())

    assert metrics["failed_count"] == 1
    assert metrics["applied_count"] == 0
