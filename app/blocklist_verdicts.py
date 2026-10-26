"""Controlled internal producer for explicit blocklist verdicts."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping

from app.blocklist_sync import BlockVerdict, VerdictValidationError


class BlocklistVerdictProducer:
    """Validate and enqueue explicit policy verdicts.

    Call submit from the asyncio event loop that owns verdict_queue.
    No detection event is automatically translated into a block decision.
    """

    def __init__(
        self,
        verdict_queue: asyncio.Queue,
        *,
        enabled: bool = False,
    ) -> None:
        self.verdict_queue = verdict_queue
        self.enabled = enabled
        self.submitted_count = 0
        self.rejected_count = 0
        self.disabled_count = 0
        self.queue_full_count = 0

    async def submit(self, payload: object) -> dict:
        if not self.enabled:
            self.disabled_count += 1
            return {"accepted": False, "reason": "disabled"}

        try:
            verdict = BlockVerdict.from_payload(payload)
        except VerdictValidationError as exc:
            self.rejected_count += 1
            return {
                "accepted": False,
                "reason": "invalid_verdict",
                "detail": str(exc),
            }

        # Queue only canonical, validated fields.
        canonical = {
            "verdict_id": verdict.verdict_id,
            "action": verdict.action,
            "source_ip": str(verdict.source_ip),
            "rule_id": verdict.rule_id,
            "issued_at_ns": verdict.issued_at_ns,
            "expires_at_ns": verdict.expires_at_ns,
        }
        if verdict.detected_at_monotonic_ns is not None:
            canonical["detected_at_monotonic_ns"] = verdict.detected_at_monotonic_ns

        try:
            self.verdict_queue.put_nowait(canonical)
        except asyncio.QueueFull:
            self.queue_full_count += 1
            return {"accepted": False, "reason": "queue_full"}

        self.submitted_count += 1
        return {
            "accepted": True,
            "verdict_id": verdict.verdict_id,
            "queue_depth": self.verdict_queue.qsize(),
        }

    def snapshot(self) -> dict:
        return {
            "producer_enabled": self.enabled,
            "submitted_count": self.submitted_count,
            "rejected_count": self.rejected_count,
            "disabled_count": self.disabled_count,
            "queue_full_count": self.queue_full_count,
            "submission_queue_depth": self.verdict_queue.qsize(),
            "submission_queue_capacity": self.verdict_queue.maxsize,
        }
