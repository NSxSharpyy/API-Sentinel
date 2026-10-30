"""Validated asynchronous worker for kernel blocklist verdicts.

The kernel map writer is injected deliberately. This module does not load,
pin, modify, or attach any eBPF program by itself.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import time
from collections import OrderedDict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

logger = logging.getLogger(__name__)


def _nearest_rank_percentile(sorted_values: list[float], percentile: float) -> float:
    """Return a nearest-rank percentile from an already sorted sample list."""
    if not sorted_values:
        return 0.0
    index = max(0, math.ceil(percentile * len(sorted_values)) - 1)
    return sorted_values[index]


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
    detected_at_monotonic_ns: int | None = None

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

        detected_at_monotonic_ns = payload.get("detected_at_monotonic_ns")
        if detected_at_monotonic_ns is not None and (
            isinstance(detected_at_monotonic_ns, bool)
            or not isinstance(detected_at_monotonic_ns, int)
            or detected_at_monotonic_ns <= 0
        ):
            raise VerdictValidationError(
                "detected_at_monotonic_ns must be a positive integer"
            )

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
            detected_at_monotonic_ns=detected_at_monotonic_ns,
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
        batch_size: int = 64,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be positive")
        if dedupe_limit < 1:
            raise ValueError("dedupe_limit must be at least 1")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        self.verdict_queue = verdict_queue
        self.map_writer = map_writer
        self.poll_interval_s = poll_interval_s
        self.dedupe_limit = dedupe_limit
        self.batch_size = batch_size
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._detection_to_apply_samples_ms: deque[float] = deque(maxlen=10_000)

        self._metrics = {
            "received_count": 0,
            "applied_count": 0,
            "rejected_count": 0,
            "duplicate_count": 0,
            "failed_count": 0,
            "last_apply_latency_ms": 0.0,
            "total_apply_latency_ms": 0.0,
            "detection_to_apply_sample_count": 0,
            "last_detection_to_apply_latency_ms": 0.0,
            "total_detection_to_apply_latency_ms": 0.0,
            "max_detection_to_apply_latency_ms": 0.0,
            "detection_to_apply_over_1ms_count": 0,
            "detection_to_apply_invalid_clock_count": 0,
            "last_error_type": None,
        }

    def _apply_batch_with_timestamps(
        self,
        payloads: list[object],
        seen: OrderedDict[str, None],
    ) -> tuple[list[dict[str, object]], OrderedDict[str, None]]:
        """Validate and apply ordered verdicts, using optional writer batching."""
        results: list[dict[str, object] | None] = [None] * len(payloads)
        index = 0

        while index < len(payloads):
            try:
                verdict = BlockVerdict.from_payload(payloads[index])
            except VerdictValidationError as exc:
                results[index] = {"status": "rejected", "error": exc}
                index += 1
                continue
            except Exception as exc:
                results[index] = {"status": "failed", "error": exc}
                index += 1
                continue

            if verdict.verdict_id in seen:
                results[index] = {"status": "duplicate", "verdict": verdict}
                index += 1
                continue

            # Never put the same verdict ID into one call: if the first
            # application fails, a later occurrence must still be retryable.
            group_indices = [index]
            group_verdicts = [verdict]
            group_ids = {verdict.verdict_id}
            cursor = index + 1

            while cursor < len(payloads) and len(group_verdicts) < self.batch_size:
                try:
                    candidate = BlockVerdict.from_payload(payloads[cursor])
                except Exception:
                    # Process this item separately so its precise error status
                    # is retained and earlier operations remain ordered.
                    break

                if (
                    candidate.verdict_id in seen
                    or candidate.verdict_id in group_ids
                ):
                    break

                group_indices.append(cursor)
                group_verdicts.append(candidate)
                group_ids.add(candidate.verdict_id)
                cursor += 1

            apply_many = getattr(self.map_writer, "apply_many", None)

            if callable(apply_many):
                started_ns = time.monotonic_ns()
                try:
                    errors = apply_many(group_verdicts)
                    if not isinstance(errors, (list, tuple)) or len(errors) != len(
                        group_verdicts
                    ):
                        raise RuntimeError(
                            "apply_many returned an invalid result count"
                        )
                    errors = [
                        error if error is None or isinstance(error, Exception)
                        else RuntimeError("apply_many returned an invalid error")
                        for error in errors
                    ]
                except Exception as exc:
                    errors = [exc] * len(group_verdicts)
                completed_ns = time.monotonic_ns()

                for item_index, item, error in zip(
                    group_indices, group_verdicts, errors
                ):
                    if error is not None:
                        results[item_index] = {
                            "status": "failed",
                            "verdict": item,
                            "error": error,
                        }
                        continue

                    self._remember(item.verdict_id, seen)
                    results[item_index] = {
                        "status": "applied",
                        "verdict": item,
                        "started_ns": started_ns,
                        "completed_ns": completed_ns,
                    }
            else:
                # Compatibility path for existing writers and test doubles.
                for item_index, item in zip(group_indices, group_verdicts):
                    started_ns = time.monotonic_ns()
                    try:
                        self.map_writer.apply(item)
                    except Exception as exc:
                        results[item_index] = {
                            "status": "failed",
                            "verdict": item,
                            "error": exc,
                        }
                        continue

                    completed_ns = time.monotonic_ns()
                    self._remember(item.verdict_id, seen)
                    results[item_index] = {
                        "status": "applied",
                        "verdict": item,
                        "started_ns": started_ns,
                        "completed_ns": completed_ns,
                    }

            index += len(group_verdicts)

        # Every input slot is filled by the ordered processing loop above.
        return [result for result in results if result is not None], seen

    async def run(self, stop_event: asyncio.Event) -> None:
        """Consume ordered batches while accounting for every queue item."""
        logger.info("Blocklist synchronization worker started")

        while True:
            if stop_event.is_set() and self.verdict_queue.empty():
                break

            try:
                first = await asyncio.wait_for(
                    self.verdict_queue.get(),
                    timeout=self.poll_interval_s,
                )
            except TimeoutError:
                if stop_event.is_set() and self.verdict_queue.empty():
                    break
                continue

            payloads = [first]
            while len(payloads) < self.batch_size:
                try:
                    payloads.append(self.verdict_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            self._metrics["received_count"] += len(payloads)
            seen_snapshot = OrderedDict(self._seen)

            try:
                apply_task = asyncio.create_task(
                    asyncio.to_thread(
                        self._apply_batch_with_timestamps,
                        payloads,
                        seen_snapshot,
                    ),
                    name="api-sentinel-blocklist-map-apply",
                )
                try:
                    results, updated_seen = await asyncio.shield(apply_task)
                except asyncio.CancelledError:
                    logger.warning(
                        "Cancellation received during blocklist map update; "
                        "waiting for the in-flight update to finish"
                    )
                    try:
                        await asyncio.shield(apply_task)
                    except Exception:
                        logger.exception(
                            "In-flight blocklist map update failed during shutdown"
                        )
                    raise
                self._seen = updated_seen

                for result in results:
                    status = result["status"]

                    if status == "rejected":
                        exc = result["error"]
                        self._metrics["rejected_count"] += 1
                        self._metrics["last_error_type"] = type(exc).__name__
                        logger.warning("Rejected block verdict: %s", exc)
                        continue

                    if status == "duplicate":
                        self._metrics["duplicate_count"] += 1
                        continue

                    if status == "failed":
                        exc = result["error"]
                        self._metrics["failed_count"] += 1
                        self._metrics["last_error_type"] = type(exc).__name__
                        logger.error("Blocklist map update failed: %s", exc)
                        continue

                    verdict = result["verdict"]
                    started_ns = result["started_ns"]
                    completed_ns = result["completed_ns"]

                    apply_latency_ms = (completed_ns - started_ns) / 1_000_000
                    self._metrics["applied_count"] += 1
                    self._metrics["last_apply_latency_ms"] = apply_latency_ms
                    self._metrics["total_apply_latency_ms"] += apply_latency_ms

                    detected_ns = verdict.detected_at_monotonic_ns
                    if detected_ns is not None:
                        detection_to_apply_ms = (
                            completed_ns - detected_ns
                        ) / 1_000_000

                        if detection_to_apply_ms >= 0:
                            self._detection_to_apply_samples_ms.append(
                                detection_to_apply_ms
                            )
                            self._metrics["detection_to_apply_sample_count"] += 1
                            self._metrics["last_detection_to_apply_latency_ms"] = (
                                detection_to_apply_ms
                            )
                            self._metrics["total_detection_to_apply_latency_ms"] += (
                                detection_to_apply_ms
                            )
                            self._metrics["max_detection_to_apply_latency_ms"] = max(
                                self._metrics["max_detection_to_apply_latency_ms"],
                                detection_to_apply_ms,
                            )
                            if detection_to_apply_ms > 1.0:
                                self._metrics["detection_to_apply_over_1ms_count"] += 1
                        else:
                            self._metrics["detection_to_apply_invalid_clock_count"] += 1

                    self._metrics["last_error_type"] = None

            except Exception as exc:
                # The per-verdict path handles expected validation/writer
                # errors. This branch protects queue accounting if the batch
                # worker itself fails unexpectedly.
                self._metrics["failed_count"] += len(payloads)
                self._metrics["last_error_type"] = type(exc).__name__
                logger.exception("Blocklist batch processing failed")

            finally:
                for _ in payloads:
                    self.verdict_queue.task_done()

        logger.info("Blocklist synchronization worker stopped")

    def _remember(
        self,
        verdict_id: str,
        seen: OrderedDict[str, None] | None = None,
    ) -> None:
        target = self._seen if seen is None else seen
        target[verdict_id] = None
        target.move_to_end(verdict_id)

        while len(target) > self.dedupe_limit:
            target.popitem(last=False)

    def snapshot(self) -> dict:
        """Return a copy of worker counters for diagnostics."""
        result = dict(self._metrics)
        count = result["applied_count"]
        result["average_apply_latency_ms"] = (
            result["total_apply_latency_ms"] / count if count else 0.0
        )
        detection_count = result["detection_to_apply_sample_count"]
        result["average_detection_to_apply_latency_ms"] = (
            result["total_detection_to_apply_latency_ms"] / detection_count
            if detection_count
            else 0.0
        )
        samples = sorted(self._detection_to_apply_samples_ms)
        result["detection_to_apply_window_sample_count"] = len(samples)
        for percentile in (50, 95, 99):
            result[f"detection_to_apply_p{percentile}_latency_ms"] = (
                _nearest_rank_percentile(samples, percentile / 100)
            )
        result["queue_depth"] = self.verdict_queue.qsize()
        return result
