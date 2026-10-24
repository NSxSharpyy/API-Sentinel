"""Validated asynchronous worker for kernel blocklist verdicts.

The kernel map writer is injected deliberately. This module does not load,
pin, modify, or attach any eBPF program by itself.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

logger = logging.getLogger(__name__)


class VerdictValidationError(ValueError):
    """Raised when an incoming block verdict is invalid."""


@dataclass(frozen=True, slots=True)
class BlockVerdict:
    verdict_id: str
    action: Literal["block", "unblock"]
    source_ip: ipaddress.IPv4Address
    rule_id: str
    issued_at_ns: int
    expires_at_ns: int | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "BlockVerdict":
        """Validate and parse a verdict received from a queue."""
        if not isinstance(payload, Mapping):
            raise VerdictValidationError("Verdict must be an object")

        verdict_id = payload.get("verdict_id")
        if not isinstance(verdict_id, str) or not verdict_id.strip():
            raise VerdictValidationError("verdict_id is required")
        if len(verdict_id) > 128:
            raise VerdictValidationError("verdict_id is too long")

        action = payload.get("action")
        if action not in ("block", "unblock"):
            raise VerdictValidationError("action must be block or unblock")

        rule_id = payload.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise VerdictValidationError("rule_id is required")
        if len(rule_id) > 128:
            raise VerdictValidationError("rule_id is too long")

        raw_ip = payload.get("source_ip")
        if not isinstance(raw_ip, str):
            raise VerdictValidationError("source_ip must be a string")

        try:
            address = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise VerdictValidationError("source_ip is invalid") from exc

        if not isinstance(address, ipaddress.IPv4Address):
            raise VerdictValidationError("only IPv4 verdicts are supported")

        # Never accept a verdict that could block the local loopback interface.
        if (
            address.is_loopback
            or address.is_unspecified
            or address.is_multicast
            or address == ipaddress.IPv4Address("255.255.255.255")
        ):
            raise VerdictValidationError("source_ip is not eligible for blocking")

        issued_at_ns = payload.get("issued_at_ns")
        if (
            isinstance(issued_at_ns, bool)
            or not isinstance(issued_at_ns, int)
            or issued_at_ns <= 0
        ):
            raise VerdictValidationError("issued_at_ns must be a positive integer")

        expires_at_ns = payload.get("expires_at_ns")
        if expires_at_ns is not None:
            if (
                isinstance(expires_at_ns, bool)
                or not isinstance(expires_at_ns, int)
                or expires_at_ns <= issued_at_ns
            ):
                raise VerdictValidationError(
                    "expires_at_ns must be later than issued_at_ns"
                )
            if expires_at_ns <= time.time_ns():
                raise VerdictValidationError("verdict has already expired")

        if action == "unblock" and expires_at_ns is not None:
            raise VerdictValidationError(
                "unblock verdicts must not specify expires_at_ns"
            )

        return cls(
            verdict_id=verdict_id,
            action=action,
            source_ip=address,
            rule_id=rule_id,
            issued_at_ns=issued_at_ns,
            expires_at_ns=expires_at_ns,
        )


class BlocklistMapWriter(Protocol):
    """Interface implemented by a real or test blocklist map writer."""

    def apply(self, verdict: BlockVerdict) -> None:
        """Apply one validated verdict to the configured map."""


class BlocklistSynchronizer:
    """Consume verdicts and send them to an injected map writer."""

    def __init__(
        self,
        verdict_queue: asyncio.Queue,
        map_writer: BlocklistMapWriter,
        *,
        poll_interval_s: float = 0.1,
        dedupe_limit: int = 10_000,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be positive")
        if dedupe_limit < 1:
            raise ValueError("dedupe_limit must be at least 1")

        self.verdict_queue = verdict_queue
        self.map_writer = map_writer
        self.poll_interval_s = poll_interval_s
        self.dedupe_limit = dedupe_limit
        self._seen: OrderedDict[str, None] = OrderedDict()

        self._metrics = {
            "received_count": 0,
            "applied_count": 0,
            "rejected_count": 0,
            "duplicate_count": 0,
            "failed_count": 0,
            "last_apply_latency_ms": 0.0,
            "total_apply_latency_ms": 0.0,
            "last_error_type": None,
        }

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run until stop_event is set; account for every dequeued item."""
        logger.info("Blocklist synchronization worker started")

        while True:
            if stop_event.is_set() and self.verdict_queue.empty():
                break

            try:
                payload = await asyncio.wait_for(
                    self.verdict_queue.get(),
                    timeout=self.poll_interval_s,
                )
            except TimeoutError:
                if stop_event.is_set() and self.verdict_queue.empty():
                    break
                continue

            try:
                self._metrics["received_count"] += 1
                verdict = BlockVerdict.from_payload(payload)

                if verdict.verdict_id in self._seen:
                    self._metrics["duplicate_count"] += 1
                    continue

                started_ns = time.monotonic_ns()

                # Keep a potentially blocking map operation off the event loop.
                await asyncio.to_thread(self.map_writer.apply, verdict)

                latency_ms = (time.monotonic_ns() - started_ns) / 1_000_000
                self._metrics["applied_count"] += 1
                self._metrics["last_apply_latency_ms"] = latency_ms
                self._metrics["total_apply_latency_ms"] += latency_ms
                self._metrics["last_error_type"] = None
                self._remember(verdict.verdict_id)

            except VerdictValidationError as exc:
                self._metrics["rejected_count"] += 1
                self._metrics["last_error_type"] = type(exc).__name__
                logger.warning("Rejected block verdict: %s", exc)

            except Exception as exc:
                self._metrics["failed_count"] += 1
                self._metrics["last_error_type"] = type(exc).__name__
                logger.exception("Blocklist map update failed")

            finally:
                self.verdict_queue.task_done()

        logger.info("Blocklist synchronization worker stopped")

    def _remember(self, verdict_id: str) -> None:
        self._seen[verdict_id] = None
        self._seen.move_to_end(verdict_id)

        while len(self._seen) > self.dedupe_limit:
            self._seen.popitem(last=False)

    def snapshot(self) -> dict:
        """Return a copy of worker counters for diagnostics."""
        result = dict(self._metrics)
        count = result["applied_count"]
        result["average_apply_latency_ms"] = (
            result["total_apply_latency_ms"] / count if count else 0.0
        )
        result["queue_depth"] = self.verdict_queue.qsize()
        return result
