import asyncio
import time

import pytest
import zmq
import zmq.asyncio

from app.blocklist_verdict_receiver import BlocklistVerdictReceiver


class FakeProducer:
    def __init__(self):
        self.payloads = []

    async def submit(self, payload):
        self.payloads.append(payload)
        return {"accepted": True, "verdict_id": payload["verdict_id"]}


def valid_payload():
    now = time.time_ns()
    return {
        "verdict_id": f"receiver-test-{now}",
        "action": "block",
        "source_ip": "203.0.113.25",
        "rule_id": "receiver-test-rule",
        "issued_at_ns": now,
        "expires_at_ns": now + 60_000_000_000,
    }


async def wait_until(predicate, timeout_s=2.0):
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("Timed out waiting for receiver")
        await asyncio.sleep(0.01)


def test_receiver_requires_loopback_bind():
    with pytest.raises(ValueError, match="loopback"):
        BlocklistVerdictReceiver(
            FakeProducer(),
            endpoint="tcp://0.0.0.0:5558",
        )


def test_receiver_forwards_valid_json_to_producer():
    async def scenario():
        producer = FakeProducer()
        receiver = BlocklistVerdictReceiver(
            producer,
            endpoint="tcp://127.0.0.1:*",
            poll_interval_ms=10,
        )
        sender = zmq.asyncio.Context.instance().socket(zmq.PUSH)
        sender.setsockopt(zmq.LINGER, 0)
        sender.connect(receiver.endpoint)

        stop_event = asyncio.Event()
        task = asyncio.create_task(receiver.run(stop_event))

        try:
            # Allow the local PUSH/PULL connection to establish.
            await asyncio.sleep(0.1)
            payload = valid_payload()
            await sender.send_json(payload)

            await wait_until(
                lambda: receiver.snapshot()["receiver_messages_received"] == 1
            )

            assert producer.payloads == [payload]
            snapshot = receiver.snapshot()
            assert snapshot["receiver_messages_accepted"] == 1
            assert snapshot["receiver_messages_rejected"] == 0
            assert snapshot["receiver_malformed_messages"] == 0
        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=1.0)
            sender.close(linger=0)
            receiver.close()

    asyncio.run(scenario())


def test_receiver_counts_malformed_json():
    async def scenario():
        producer = FakeProducer()
        receiver = BlocklistVerdictReceiver(
            producer,
            endpoint="tcp://127.0.0.1:*",
            poll_interval_ms=10,
        )
        sender = zmq.asyncio.Context.instance().socket(zmq.PUSH)
        sender.setsockopt(zmq.LINGER, 0)
        sender.connect(receiver.endpoint)

        stop_event = asyncio.Event()
        task = asyncio.create_task(receiver.run(stop_event))

        try:
            await asyncio.sleep(0.1)
            await sender.send(b"{invalid-json")

            await wait_until(
                lambda: receiver.snapshot()["receiver_malformed_messages"] == 1
            )

            snapshot = receiver.snapshot()
            assert snapshot["receiver_messages_received"] == 1
            assert snapshot["receiver_messages_rejected"] == 1
            assert producer.payloads == []
        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=1.0)
            sender.close(linger=0)
            receiver.close()

    asyncio.run(scenario())
