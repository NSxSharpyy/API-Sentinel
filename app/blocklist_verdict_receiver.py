"""Loopback-only ZeroMQ receiver for explicit blocklist verdicts."""
from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlsplit

import zmq
import zmq.asyncio

from app.blocklist_verdicts import BlocklistVerdictProducer

logger = logging.getLogger(__name__)

DEFAULT_VERDICT_ENDPOINT = "tcp://127.0.0.1:5558"
MAX_VERDICT_BYTES = 16_384
RECEIVE_HIGH_WATER_MARK = 1024


class BlocklistVerdictReceiver:
    """Receive JSON verdicts and submit them to the validated producer.

    This receiver only accepts a TCP endpoint bound to IPv4 loopback.
    It does not decide whether an incident should be blocked.
    """

    def __init__(
        self,
        producer: BlocklistVerdictProducer,
        endpoint: str = DEFAULT_VERDICT_ENDPOINT,
        poll_interval_ms: int = 100,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "tcp" or parsed.hostname != "127.0.0.1":
            raise ValueError(
                "Verdict receiver must bind to IPv4 loopback (tcp://127.0.0.1)"
            )
        if poll_interval_ms <= 0:
            raise ValueError("poll_interval_ms must be positive")

        self.producer = producer
        self.poll_interval_ms = poll_interval_ms
        self.context = zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.RCVHWM, RECEIVE_HIGH_WATER_MARK)
        self.socket.setsockopt(zmq.MAXMSGSIZE, MAX_VERDICT_BYTES)

        try:
            self.socket.bind(endpoint)
            self.endpoint = self.socket.getsockopt_string(zmq.LAST_ENDPOINT)
        except Exception:
            self.socket.close(linger=0)
            raise

        self._closed = False
        self._metrics = {
            "messages_received": 0,
            "messages_accepted": 0,
            "messages_rejected": 0,
            "malformed_messages": 0,
            "last_error_type": None,
            "last_rejection_reason": None,
        }

    async def run(self, stop_event: asyncio.Event) -> None:
        """Receive until shutdown is requested."""
        logger.info("Blocklist verdict receiver listening on %s", self.endpoint)

        while not stop_event.is_set():
            try:
                ready = await self.socket.poll(
                    self.poll_interval_ms, zmq.POLLIN
                )
                if not ready:
                    continue

                raw = await self.socket.recv()
                self._metrics["messages_received"] += 1

                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._metrics["malformed_messages"] += 1
                    self._metrics["messages_rejected"] += 1
                    self._metrics["last_error_type"] = "InvalidJSON"
                    self._metrics["last_rejection_reason"] = "invalid_json"
                    continue

                result = await self.producer.submit(payload)

                if result.get("accepted"):
                    self._metrics["messages_accepted"] += 1
                    self._metrics["last_error_type"] = None
                    self._metrics["last_rejection_reason"] = None
                else:
                    self._metrics["messages_rejected"] += 1
                    self._metrics["last_rejection_reason"] = str(
                        result.get("reason", "rejected")
                    )
                    self._metrics["last_error_type"] = (
                        "VerdictRejected"
                    )

            except asyncio.CancelledError:
                raise
            except zmq.ZMQError as exc:
                if stop_event.is_set() or self._closed:
                    break
                self._metrics["last_error_type"] = type(exc).__name__
                logger.exception("ZeroMQ verdict receiver error")
                await asyncio.sleep(0.05)
            except Exception as exc:
                self._metrics["last_error_type"] = type(exc).__name__
                logger.exception("Unexpected verdict receiver error")
                await asyncio.sleep(0.05)

        logger.info("Blocklist verdict receiver stopped")

    def snapshot(self) -> dict:
        """Return receiver counters without exposing verdict contents."""
        return {
            "receiver_endpoint": self.endpoint,
            "receiver_messages_received": self._metrics["messages_received"],
            "receiver_messages_accepted": self._metrics["messages_accepted"],
            "receiver_messages_rejected": self._metrics["messages_rejected"],
            "receiver_malformed_messages": self._metrics["malformed_messages"],
            "receiver_last_error_type": self._metrics["last_error_type"],
            "receiver_last_rejection_reason":
                self._metrics["last_rejection_reason"],
        }

    def close(self) -> None:
        """Close this socket without terminating the shared ZMQ context."""
        if not self._closed:
            self._closed = True
            self.socket.close(linger=0)
