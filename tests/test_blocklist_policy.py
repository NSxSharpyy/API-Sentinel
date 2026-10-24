import asyncio
import time

import pytest

from app.blocklist_policy import (
    BOLA_INCIDENT_TITLE,
    BOLA_RULE_ID,
    BlocklistPolicy,
    ThreadOwnedVerdictSender,
)


class FakeSender:
    def __init__(self, payloads=None, error=None):
        self.payloads = payloads if payloads is not None else []
        self.error = error

    def send(self, payload):
        if self.error is not None:
            raise self.error
        self.payloads.append(dict(payload))
        return payload["verdict_id"]


def detected_outcome(**overrides):
    incident = {
        "incident_id": 41,
        "severity": "high",
        "title": BOLA_INCIDENT_TITLE,
        "source_ip": "203.0.113.25",
    }
    incident.update(overrides)
    return {"detected": True, "incident": incident}


def test_disabled_policy_never_sends():
    sender = FakeSender()
    policy = BlocklistPolicy(sender, [], enabled=False)
    result = policy.evaluate(detected_outcome())
    assert result == {"accepted": False, "reason": "disabled"}
    assert sender.payloads == []


def test_enabled_policy_requires_exact_allowlist():
    with pytest.raises(ValueError, match="exact IP allowlist"):
        BlocklistPolicy(FakeSender(), [], enabled=True)


def test_allowlisted_bola_submits_short_lived_block():
    sender = FakeSender()
    policy = BlocklistPolicy(
        sender, ["203.0.113.25"], enabled=True, ttl_seconds=60
    )
    result = policy.evaluate(detected_outcome())

    assert result == {"accepted": True, "verdict_id": "bola-41-block"}
    assert len(sender.payloads) == 1
    verdict = sender.payloads[0]
    assert verdict["action"] == "block"
    assert verdict["source_ip"] == "203.0.113.25"
    assert verdict["rule_id"] == BOLA_RULE_ID
    assert verdict["expires_at_ns"] - verdict["issued_at_ns"] == 60_000_000_000


def test_non_allowlisted_source_is_not_sent():
    sender = FakeSender()
    policy = BlocklistPolicy(sender, ["203.0.113.25"], enabled=True)
    result = policy.evaluate(detected_outcome(source_ip="203.0.113.26"))
    assert result["reason"] == "source_ip_not_allowlisted"
    assert sender.payloads == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "Different incident"},
        {"severity": "medium"},
        {"source_ip": "127.0.0.1"},
        {"source_ip": "not-an-ip"},
        {"incident_id": 0},
    ],
)
def test_nonmatching_or_ineligible_incident_never_sends(overrides):
    sender = FakeSender()
    policy = BlocklistPolicy(sender, ["203.0.113.25"], enabled=True)
    result = policy.evaluate(detected_outcome(**overrides))
    assert result["accepted"] is False
    assert sender.payloads == []


def test_non_detection_never_sends():
    sender = FakeSender()
    policy = BlocklistPolicy(sender, ["203.0.113.25"], enabled=True)
    assert policy.evaluate({"detected": False})["reason"] == "not_detected"
    assert sender.payloads == []


def test_sender_error_is_counted_without_raising():
    policy = BlocklistPolicy(
        FakeSender(error=TimeoutError("no receiver")),
        ["203.0.113.25"],
        enabled=True,
    )
    result = policy.evaluate(detected_outcome())
    assert result == {"accepted": False, "reason": "sender_error"}
    assert policy.snapshot()["failed_count"] == 1
    assert policy.snapshot()["last_error_type"] == "TimeoutError"


def test_bad_allowlist_address_is_rejected():
    with pytest.raises(ValueError, match="not eligible for blocking"):
        BlocklistPolicy(FakeSender(), ["127.0.0.1"], enabled=True)


def test_ttl_is_bounded():
    with pytest.raises(ValueError, match="ttl_seconds"):
        BlocklistPolicy(FakeSender(), ["203.0.113.25"], enabled=True, ttl_seconds=3601)


def test_thread_owned_sender_uses_one_worker_thread():
    import threading

    made_on = []
    used_on = []
    closed_on = []

    class ContextSender:
        def __enter__(self):
            made_on.append(threading.get_ident())
            return self

        def send(self, payload):
            used_on.append(threading.get_ident())
            return payload["verdict_id"]

        def __exit__(self, exc_type, exc, tb):
            closed_on.append(threading.get_ident())
            return False

    sender = ThreadOwnedVerdictSender(ContextSender)
    try:
        assert sender.send({"verdict_id": "thread-test"}) == "thread-test"
    finally:
        sender.close()

    assert len(set(made_on + used_on + closed_on)) == 1


def test_policy_real_sender_delivers_to_loopback_receiver_queue():
    import asyncio

    from app.blocklist_policy import (
        BOLA_INCIDENT_TITLE,
        BOLA_RULE_ID,
        BlocklistPolicy,
        ThreadOwnedVerdictSender,
    )
    from app.blocklist_verdict_client import BlocklistVerdictSender
    from app.blocklist_verdict_receiver import BlocklistVerdictReceiver
    from app.blocklist_verdicts import BlocklistVerdictProducer

    async def scenario():
        verdict_queue = asyncio.Queue(maxsize=8)
        producer = BlocklistVerdictProducer(verdict_queue, enabled=True)
        receiver = BlocklistVerdictReceiver(
            producer,
            endpoint="tcp://127.0.0.1:*",
            poll_interval_ms=10,
        )
        stop_event = asyncio.Event()
        receiver_task = asyncio.create_task(receiver.run(stop_event))
        sender = None

        try:
            sender = ThreadOwnedVerdictSender(
                lambda: BlocklistVerdictSender(endpoint=receiver.endpoint)
            )
            policy = BlocklistPolicy(
                sender,
                ["203.0.113.25"],
                enabled=True,
                ttl_seconds=60,
            )

            # Give the loopback PUSH/PULL connection time to establish.
            await asyncio.sleep(0.15)

            outcome = {
                "detected": True,
                "incident": {
                    "incident_id": 41,
                    "severity": "high",
                    "title": BOLA_INCIDENT_TITLE,
                    "source_ip": "203.0.113.25",
                },
            }
            result = await asyncio.to_thread(policy.evaluate, outcome)
            assert result == {
                "accepted": True,
                "verdict_id": "bola-41-block",
            }

            deadline = asyncio.get_running_loop().time() + 2.0
            while (
                receiver.snapshot()["receiver_messages_accepted"] < 1
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)

            snapshot = receiver.snapshot()
            assert snapshot["receiver_messages_received"] == 1
            assert snapshot["receiver_messages_accepted"] == 1
            assert snapshot["receiver_messages_rejected"] == 0
            assert producer.snapshot()["submitted_count"] == 1
            assert verdict_queue.qsize() == 1

            queued = verdict_queue.get_nowait()
            try:
                assert queued["verdict_id"] == "bola-41-block"
                assert queued["action"] == "block"
                assert queued["source_ip"] == "203.0.113.25"
                assert queued["rule_id"] == BOLA_RULE_ID
                assert (
                    queued["expires_at_ns"] - queued["issued_at_ns"]
                    == 60_000_000_000
                )
            finally:
                verdict_queue.task_done()

        finally:
            if sender is not None:
                sender.close()
            stop_event.set()
            try:
                await asyncio.wait_for(receiver_task, timeout=1.0)
            finally:
                receiver.close()

    asyncio.run(scenario())
