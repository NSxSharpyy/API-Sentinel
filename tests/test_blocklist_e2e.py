"""End-to-end policy -> ZeroMQ -> queue -> synchronizer integration test."""
from __future__ import annotations

import asyncio

from app.blocklist_policy import (
    BOLA_INCIDENT_TITLE,
    BOLA_RULE_ID,
    BlocklistPolicy,
    ThreadOwnedVerdictSender,
)
from app.blocklist_sync import BlocklistSynchronizer, BlockVerdict
from app.blocklist_verdict_client import BlocklistVerdictSender
from app.blocklist_verdict_receiver import BlocklistVerdictReceiver
from app.blocklist_verdicts import BlocklistVerdictProducer


class RecordingMapWriter:
    """Test adapter representing the kernel-map writer boundary."""

    def __init__(self):
        self.applied: list[BlockVerdict] = []

    def apply(self, verdict: BlockVerdict) -> None:
        self.applied.append(verdict)


def test_policy_verdict_reaches_synchronizer_and_map_writer_boundary():
    async def scenario():
        verdict_queue = asyncio.Queue(maxsize=8)
        producer = BlocklistVerdictProducer(verdict_queue, enabled=True)
        receiver = BlocklistVerdictReceiver(
            producer,
            endpoint="tcp://127.0.0.1:*",
            poll_interval_ms=10,
        )
        writer = RecordingMapWriter()
        synchronizer = BlocklistSynchronizer(
            verdict_queue,
            writer,
            poll_interval_s=0.01,
        )
        receiver_stop = asyncio.Event()
        sync_stop = asyncio.Event()
        receiver_task = asyncio.create_task(receiver.run(receiver_stop))
        sync_task = asyncio.create_task(synchronizer.run(sync_stop))
        sender = None

        try:
            sender = ThreadOwnedVerdictSender(
                lambda: BlocklistVerdictSender(endpoint=receiver.endpoint)
            )
            policy = BlocklistPolicy(
                sender,
                ["198.51.100.25"],
                enabled=True,
                ttl_seconds=60,
            )

            # Let the local PUSH/PULL connection establish before sending.
            await asyncio.sleep(0.15)
            outcome = {
                "detected": True,
                "incident": {
                    "incident_id": 4001,
                    "severity": "high",
                    "title": BOLA_INCIDENT_TITLE,
                    "source_ip": "198.51.100.25",
                },
            }
            result = await asyncio.to_thread(policy.evaluate, outcome)
            assert result == {
                "accepted": True,
                "verdict_id": "bola-4001-block",
            }

            deadline = asyncio.get_running_loop().time() + 2.0
            while (
                receiver.snapshot()["receiver_messages_accepted"] < 1
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)
            assert receiver.snapshot()["receiver_messages_accepted"] == 1
            await asyncio.wait_for(verdict_queue.join(), timeout=2.0)
            assert synchronizer.snapshot()["applied_count"] == 1
            assert synchronizer.snapshot()["failed_count"] == 0
            assert len(writer.applied) == 1

            verdict = writer.applied[0]
            assert verdict.verdict_id == "bola-4001-block"
            assert verdict.action == "block"
            assert str(verdict.source_ip) == "198.51.100.25"
            assert verdict.rule_id == BOLA_RULE_ID
            assert verdict.expires_at_ns is not None
            assert verdict.expires_at_ns > verdict.issued_at_ns
        finally:
            if sender is not None:
                sender.close()
            receiver_stop.set()
            try:
                await asyncio.wait_for(receiver_task, timeout=1.0)
            finally:
                receiver.close()
            sync_stop.set()
            await asyncio.wait_for(sync_task, timeout=1.0)

    asyncio.run(scenario())
