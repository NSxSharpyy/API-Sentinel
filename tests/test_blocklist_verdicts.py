import asyncio
import time

from app.blocklist_verdicts import BlocklistVerdictProducer


def make_payload(**overrides):
    payload = {
        "verdict_id": "producer-test-1",
        "action": "block",
        "source_ip": "203.0.113.25",
        "rule_id": "test-policy",
        "issued_at_ns": time.time_ns(),
        "expires_at_ns": time.time_ns() + 30_000_000_000,
    }
    payload.update(overrides)
    return payload


def test_disabled_producer_does_not_enqueue():
    async def run():
        queue = asyncio.Queue(maxsize=2)
        producer = BlocklistVerdictProducer(queue, enabled=False)
        result = await producer.submit(make_payload())

        assert result["accepted"] is False
        assert result["reason"] == "disabled"
        assert queue.qsize() == 0
        assert producer.snapshot()["disabled_count"] == 1

    asyncio.run(run())


def test_enabled_producer_enqueues_canonical_verdict():
    async def run():
        queue = asyncio.Queue(maxsize=2)
        producer = BlocklistVerdictProducer(queue, enabled=True)
        result = await producer.submit(make_payload())

        assert result["accepted"] is True
        item = queue.get_nowait()
        assert item["source_ip"] == "203.0.113.25"
        assert item["action"] == "block"
        assert item["rule_id"] == "test-policy"
        queue.task_done()
        assert producer.snapshot()["submitted_count"] == 1

    asyncio.run(run())


def test_invalid_verdict_is_rejected():
    async def run():
        queue = asyncio.Queue(maxsize=2)
        producer = BlocklistVerdictProducer(queue, enabled=True)
        result = await producer.submit(make_payload(source_ip="127.0.0.1"))

        assert result["accepted"] is False
        assert result["reason"] == "invalid_verdict"
        assert queue.empty()
        assert producer.snapshot()["rejected_count"] == 1

    asyncio.run(run())


def test_full_queue_rejects_without_blocking():
    async def run():
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait({"existing": True})
        producer = BlocklistVerdictProducer(queue, enabled=True)
        result = await producer.submit(make_payload())

        assert result["accepted"] is False
        assert result["reason"] == "queue_full"
        assert producer.snapshot()["queue_full_count"] == 1

    asyncio.run(run())
