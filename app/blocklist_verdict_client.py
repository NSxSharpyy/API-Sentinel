"""Synchronous client for sending explicit verdicts to API-Sentinel."""
from __future__ import annotations

from collections.abc import Mapping

import zmq

from app.blocklist_sync import BlockVerdict
from app.blocklist_verdict_receiver import DEFAULT_VERDICT_ENDPOINT


class BlocklistVerdictSender:
    """Persistent PUSH client for the local verdict receiver.

    Reuse one sender instance instead of creating one for each verdict.
    A successful send means ZeroMQ accepted the message for delivery; inspect
    API-Sentinel's receiver/worker metrics to confirm processing.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_VERDICT_ENDPOINT,
        send_timeout_ms: int = 1000,
    ) -> None:
        from urllib.parse import urlsplit

        parsed = urlsplit(endpoint)
        if parsed.scheme != "tcp" or parsed.hostname != "127.0.0.1":
            raise ValueError(
                "Verdict sender must connect to tcp://127.0.0.1"
            )
        if send_timeout_ms <= 0:
            raise ValueError("send_timeout_ms must be positive")

        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.PUSH)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SNDHWM, 1024)
        self.socket.setsockopt(zmq.SNDTIMEO, send_timeout_ms)
        self.socket.setsockopt(zmq.IMMEDIATE, 1)
        self.socket.connect(endpoint)
        self._closed = False

    def send(self, payload: Mapping[str, object]) -> str:
        """Validate, canonicalize, and send one block/unblock verdict."""
        if self._closed:
            raise RuntimeError("Verdict sender is closed")

        verdict = BlockVerdict.from_payload(payload)
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
        self.socket.send_json(canonical)
        return verdict.verdict_id

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.socket.close(linger=0)

    def __enter__(self) -> "BlocklistVerdictSender":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False
