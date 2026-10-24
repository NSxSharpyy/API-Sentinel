"""Explicit policy gate and thread-owned sender for lab block verdicts."""
from __future__ import annotations

import ipaddress
import logging
import queue
import threading
import time
from collections.abc import Iterable, Mapping
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Callable, Protocol

logger = logging.getLogger(__name__)

BOLA_RULE_ID = "lab_scoped_bola_invoice_owner_mismatch"
BOLA_INCIDENT_TITLE = "Potential BOLA: cross-user invoice access (lab heuristic)"
DEFAULT_VERDICT_TTL_SECONDS = 60
MAX_VERDICT_TTL_SECONDS = 3600
_STOP = object()


class VerdictSender(Protocol):
    def send(self, payload: Mapping[str, object]) -> str:
        """Send one explicit verdict."""


@dataclass
class _SendRequest:
    payload: Mapping[str, object]
    completion: Future[str]


class ThreadOwnedVerdictSender:
    """Keep the underlying ZeroMQ socket on one dedicated owner thread.

    TransactionStore.save runs via asyncio.to_thread. This wrapper lets that
    worker thread synchronously submit a request without touching the ZeroMQ
    socket itself. One persistent sender socket is reused on its owner thread.
    """

    def __init__(
        self,
        sender_factory: Callable[[], object],
        *,
        max_queue_size: int = 1024,
        startup_timeout_s: float = 2.0,
        request_timeout_s: float = 3.0,
    ) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        if startup_timeout_s <= 0 or request_timeout_s <= 0:
            raise ValueError("timeouts must be positive")

        self._sender_factory = sender_factory
        self._request_timeout_s = request_timeout_s
        self._requests: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._worker_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="api-sentinel-blocklist-sender",
            daemon=True,
        )
        self._thread.start()

        if not self._ready.wait(startup_timeout_s):
            self.close()
            raise TimeoutError("Blocklist sender thread did not initialize")
        if self._worker_error is not None:
            error = self._worker_error
            self.close()
            raise RuntimeError("Blocklist sender initialization failed") from error

    def _fail_pending(self, error: BaseException) -> None:
        while True:
            try:
                item = self._requests.get_nowait()
            except queue.Empty:
                return
            try:
                if item is not _STOP and not item.completion.done():
                    item.completion.set_exception(
                        RuntimeError("Blocklist sender worker stopped")
                    )
            finally:
                self._requests.task_done()

    def _run(self) -> None:
        try:
            # The factory and all socket operations run on this thread.
            with self._sender_factory() as sender:
                self._ready.set()
                while True:
                    item = self._requests.get()
                    try:
                        if item is _STOP:
                            return
                        if item.completion.cancelled():
                            continue
                        try:
                            result = sender.send(item.payload)
                        except Exception as exc:
                            if not item.completion.done():
                                item.completion.set_exception(exc)
                        else:
                            if not item.completion.done():
                                item.completion.set_result(result)
                    finally:
                        self._requests.task_done()
        except BaseException as exc:
            self._worker_error = exc
            self._ready.set()
            self._fail_pending(exc)
            if isinstance(exc, Exception):
                logger.error(
                    "Blocklist sender worker stopped (%s)",
                    type(exc).__name__,
                )

    def send(self, payload: Mapping[str, object]) -> str:
        request = _SendRequest(dict(payload), Future())
        with self._lock:
            if self._closed:
                raise RuntimeError("Blocklist sender is closed")
            if self._worker_error is not None or not self._thread.is_alive():
                raise RuntimeError("Blocklist sender worker is unavailable")
            try:
                self._requests.put(
                    request, timeout=self._request_timeout_s
                )
            except queue.Full as exc:
                raise TimeoutError("Blocklist sender queue is full") from exc

        try:
            return request.completion.result(timeout=self._request_timeout_s)
        except FutureTimeoutError as exc:
            request.completion.cancel()
            raise TimeoutError(
                "Blocklist send timed out; delivery outcome may be uncertain"
            ) from exc

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._thread.is_alive():
                try:
                    self._requests.put(
                        _STOP, timeout=self._request_timeout_s
                    )
                except queue.Full:
                    logger.error("Unable to enqueue blocklist sender shutdown")
                    return

        self._thread.join(timeout=self._request_timeout_s)
        if self._thread.is_alive():
            logger.error("Blocklist sender thread did not stop cleanly")

    def __enter__(self) -> "ThreadOwnedVerdictSender":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False


def _eligible_ipv4(value: object) -> ipaddress.IPv4Address:
    if not isinstance(value, str):
        raise ValueError("source IP must be a string")
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError("invalid source IP") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise ValueError("only IPv4 source IPs are supported")
    if (
        address.is_loopback
        or address.is_unspecified
        or address.is_multicast
        or address == ipaddress.IPv4Address("255.255.255.255")
    ):
        raise ValueError("source IP is not eligible for blocking")
    return address


class BlocklistPolicy:
    """Block only exact-allowlisted sources matching the lab BOLA heuristic."""

    def __init__(
        self,
        sender: VerdictSender | None,
        allowed_source_ips: Iterable[str],
        *,
        enabled: bool = False,
        ttl_seconds: int = DEFAULT_VERDICT_TTL_SECONDS,
    ) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise ValueError("ttl_seconds must be an integer")
        if not 1 <= ttl_seconds <= MAX_VERDICT_TTL_SECONDS:
            raise ValueError(
                f"ttl_seconds must be between 1 and {MAX_VERDICT_TTL_SECONDS}"
            )

        allowed = {_eligible_ipv4(item) for item in allowed_source_ips}
        if enabled and sender is None:
            raise ValueError("enabled policy requires a sender")
        if enabled and not allowed:
            raise ValueError("enabled policy requires an exact IP allowlist")

        self.sender = sender
        self.allowed_source_ips = frozenset(allowed)
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.evaluated_count = 0
        self.submitted_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.last_decision = None
        self.last_reason = None
        self.last_error_type = None

    def _skip(self, reason: str) -> dict:
        self.skipped_count += 1
        self.last_decision = "skipped"
        self.last_reason = reason
        return {"accepted": False, "reason": reason}

    def evaluate(self, outcome: object) -> dict:
        """Evaluate a committed detection result and, if allowed, submit a block."""
        self.evaluated_count += 1

        if not self.enabled:
            return self._skip("disabled")
        if not isinstance(outcome, Mapping) or outcome.get("detected") is not True:
            return self._skip("not_detected")

        incident = outcome.get("incident")
        if not isinstance(incident, Mapping):
            return self._skip("missing_incident")
        if (
            incident.get("severity") != "high"
            or incident.get("title") != BOLA_INCIDENT_TITLE
        ):
            return self._skip("policy_rule_not_matched")

        try:
            source_ip = _eligible_ipv4(incident.get("source_ip"))
        except ValueError:
            return self._skip("invalid_source_ip")
        if source_ip not in self.allowed_source_ips:
            return self._skip("source_ip_not_allowlisted")

        incident_id = incident.get("incident_id")
        if (
            isinstance(incident_id, bool)
            or not isinstance(incident_id, int)
            or incident_id <= 0
        ):
            return self._skip("invalid_incident_id")

        if self.sender is None:
            return self._skip("sender_unavailable")

        issued_at_ns = time.time_ns()
        payload = {
            "verdict_id": f"bola-{incident_id}-block",
            "action": "block",
            "source_ip": str(source_ip),
            "rule_id": BOLA_RULE_ID,
            "issued_at_ns": issued_at_ns,
            "expires_at_ns": issued_at_ns + self.ttl_seconds * 1_000_000_000,
        }
        try:
            self.sender.send(payload)
        except Exception as exc:
            self.failed_count += 1
            self.last_decision = "failed"
            self.last_reason = "sender_error"
            self.last_error_type = type(exc).__name__
            logger.warning(
                "Blocklist verdict submission failed (%s)", type(exc).__name__
            )
            return {"accepted": False, "reason": "sender_error"}

        self.submitted_count += 1
        self.last_decision = "submitted"
        self.last_reason = "allowlisted_lab_bola"
        self.last_error_type = None
        return {"accepted": True, "verdict_id": payload["verdict_id"]}

    def snapshot(self) -> dict:
        """Return policy metrics without exposing the configured IP addresses."""
        return {
            "enabled": self.enabled,
            "allowed_source_count": len(self.allowed_source_ips),
            "ttl_seconds": self.ttl_seconds,
            "evaluated_count": self.evaluated_count,
            "submitted_count": self.submitted_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "last_decision": self.last_decision,
            "last_reason": self.last_reason,
            "last_error_type": self.last_error_type,
        }
