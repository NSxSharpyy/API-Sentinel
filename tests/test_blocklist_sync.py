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
        {"detected_at_monotonic_ns": True},
        {"detected_at_monotonic_ns": 0},
        {"detected_at_monotonic_ns": "123"},
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




def test_batched_worker_preserves_order_and_deduplicates_within_batch():
    async def scenario():
        queue = asyncio.Queue()
        writer = RecordingWriter()
        worker = BlocklistSynchronizer(queue, writer, batch_size=8)
        stop_event = asyncio.Event()
        task = asyncio.create_task(worker.run(stop_event))

        payloads = [
            make_payload(verdict_id="ordered-1", action="block"),
            make_payload(verdict_id="ordered-2", action="unblock"),
            make_payload(verdict_id="ordered-1", action="block"),
            make_payload(
                verdict_id="ordered-3",
                action="block",
                source_ip="198.51.100.26",
            ),
        ]
        for payload in payloads:
            queue.put_nowait(payload)

        await asyncio.wait_for(queue.join(), timeout=2)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2)
        return writer.applied, worker.snapshot()

    applied, metrics = asyncio.run(scenario())

    assert [verdict.verdict_id for verdict in applied] == [
        "ordered-1", "ordered-2", "ordered-3"
    ]
    assert metrics["applied_count"] == 3
    assert metrics["duplicate_count"] == 1
    assert metrics["failed_count"] == 0
    assert metrics["queue_depth"] == 0


def test_batched_worker_allows_retry_after_writer_failure():
    class FailOnceWriter:
        def __init__(self):
            self.calls = 0
            self.applied = []

        def apply(self, verdict):
            self.calls += 1
            if self.calls == 1:
                raise OSError("simulated first-attempt failure")
            self.applied.append(verdict)

    async def scenario():
        queue = asyncio.Queue()
        writer = FailOnceWriter()
        worker = BlocklistSynchronizer(queue, writer, batch_size=8)
        stop_event = asyncio.Event()
        task = asyncio.create_task(worker.run(stop_event))
        payload = make_payload(verdict_id="retry-after-failure")

        queue.put_nowait(payload)
        await asyncio.wait_for(queue.join(), timeout=2)

        # A failed verdict must not be remembered as successfully applied.
        queue.put_nowait(payload)
        await asyncio.wait_for(queue.join(), timeout=2)

        stop_event.set()
        await asyncio.wait_for(task, timeout=2)
        return writer, worker.snapshot()

    writer, metrics = asyncio.run(scenario())

    assert writer.calls == 2
    assert len(writer.applied) == 1
    assert writer.applied[0].verdict_id == "retry-after-failure"
    assert metrics["failed_count"] == 1
    assert metrics["applied_count"] == 1
    assert metrics["duplicate_count"] == 0
    assert metrics["queue_depth"] == 0


def test_synchronizer_uses_apply_many_when_available():
    class BatchRecordingWriter(RecordingWriter):
        def __init__(self):
            super().__init__()
            self.batch_calls = 0

        def apply_many(self, verdicts):
            self.batch_calls += 1
            errors = []
            for verdict in verdicts:
                try:
                    self.apply(verdict)
                except Exception as exc:
                    errors.append(exc)
                else:
                    errors.append(None)
            return errors

    async def scenario():
        queue = asyncio.Queue()
        writer = BatchRecordingWriter()
        worker = BlocklistSynchronizer(queue, writer, batch_size=8)
        stop_event = asyncio.Event()
        task = asyncio.create_task(worker.run(stop_event))

        for number in (1, 2, 3):
            queue.put_nowait(
                make_payload(
                    verdict_id=f"native-path-{number}",
                    source_ip=f"198.51.100.{number + 40}",
                )
            )

        await asyncio.wait_for(queue.join(), timeout=2)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2)
        return writer, worker.snapshot()

    writer, metrics = asyncio.run(scenario())

    assert writer.batch_calls == 1
    assert [item.verdict_id for item in writer.applied] == [
        "native-path-1", "native-path-2", "native-path-3"
    ]
    assert metrics["applied_count"] == 3
    assert metrics["failed_count"] == 0
    assert metrics["queue_depth"] == 0


def test_batch_size_must_be_positive():
    with pytest.raises(ValueError, match="batch_size"):
        BlocklistSynchronizer(
            asyncio.Queue(),
            RecordingWriter(),
            batch_size=0,
        )


def test_detection_to_apply_latency_metrics_measure_full_path():
    class SlowRecordingWriter(RecordingWriter):
        def apply(self, verdict):
            time.sleep(0.01)
            super().apply(verdict)

    async def scenario():
        queue = asyncio.Queue()
        worker = BlocklistSynchronizer(queue, SlowRecordingWriter())
        stop_event = asyncio.Event()
        task = asyncio.create_task(worker.run(stop_event))
        queue.put_nowait(
            make_payload(detected_at_monotonic_ns=time.monotonic_ns())
        )
        await asyncio.wait_for(queue.join(), timeout=2)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2)
        return worker.snapshot()

    metrics = asyncio.run(scenario())

    assert metrics["detection_to_apply_sample_count"] == 1
    assert metrics["detection_to_apply_window_sample_count"] == 1
    assert metrics["last_detection_to_apply_latency_ms"] > 1.0
    assert metrics["detection_to_apply_over_1ms_count"] == 1
    assert metrics["detection_to_apply_p50_latency_ms"] <= metrics[
        "detection_to_apply_p95_latency_ms"
    ] <= metrics["detection_to_apply_p99_latency_ms"]
