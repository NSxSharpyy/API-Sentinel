"""ZeroMQ message and completed-transaction publication contracts."""
from __future__ import annotations

import base64
import json
from datetime import timezone

import zmq

from app.http_reassembly import HTTPMessage
from app.transaction_correlator import HTTPTransaction

# Backward-compatible per-message topic. Existing consumers can continue to
# consume individual parsed request/response events from this topic.
HTTP_TRANSACTION_TOPIC = b"http.transaction"
# New downstream topics carry a complete, correlated request/response pair.
DISCOVERY_HTTP_TOPIC = b"discovery.http.transaction"
HEURISTICS_HTTP_TOPIC = b"heuristics.http.transaction"
DOWNSTREAM_HTTP_TOPICS = (
    HTTP_TRANSACTION_TOPIC,
    DISCOVERY_HTTP_TOPIC,
    HEURISTICS_HTTP_TOPIC,
)


def _captured_at_utc_iso(message: HTTPMessage) -> str | None:
    """Serialize timestamps consistently; treat legacy naive values as UTC."""
    captured_at = message.captured_at
    if captured_at is None:
        return None
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return captured_at.astimezone(timezone.utc).isoformat()


def _message_payload(message: HTTPMessage) -> dict:
    return {
        "message_type": message.message_type,
        "connection_id": message.connection_id,
        "captured_at": _captured_at_utc_iso(message),
        "method": message.method,
        "uri": message.uri,
        "status_code": message.status_code,
        "reason_phrase": message.reason_phrase,
        "version": message.version,
        "headers": message.headers,
        "body_base64": base64.b64encode(message.body).decode("ascii"),
    }


def serialize_http_message(message: HTTPMessage) -> bytes:
    """Serialize one parsed HTTP request or response as JSON."""
    event = {"event_type": "http.transaction", **_message_payload(message)}
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def serialize_http_transaction(transaction: HTTPTransaction) -> bytes:
    """Serialize a completed request/response pair for downstream analysis."""
    event = {
        "event_type": "http.transaction",
        "message_type": "completed_transaction",
        "connection_key": transaction.connection_key,
        "request": _message_payload(transaction.request),
        "response": _message_payload(transaction.response),
    }
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


class HTTPTransactionPublisher:
    """Publish parsed messages and completed transactions through ZeroMQ PUB."""

    def __init__(self, endpoint: str = "tcp://127.0.0.1:5557"):
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.bind(endpoint)

    def publish(self, message: HTTPMessage) -> None:
        """Publish one message on the legacy topic for compatibility."""
        payload = serialize_http_message(message)
        self.socket.send_multipart([HTTP_TRANSACTION_TOPIC, payload])

    def publish_transaction(self, transaction: HTTPTransaction) -> None:
        """Publish a correlated request/response pair to downstream modules.

        Discovery and heuristic consumers receive a single event containing
        both messages, avoiding ambiguous request-only/response-only routing.
        PUB/SUB remains best-effort and provides no durability or ACKs.
        """
        payload = serialize_http_transaction(transaction)
        for topic in (DISCOVERY_HTTP_TOPIC, HEURISTICS_HTTP_TOPIC):
            self.socket.send_multipart([topic, payload])

    def close(self) -> None:
        """Close the publisher socket."""
        self.socket.close()


class HTTPTransactionSubscriber:
    """Subscribe to a legacy message topic or a completed-transaction topic."""

    def __init__(
        self,
        endpoint: str = "tcp://127.0.0.1:5557",
        topic: bytes = HTTP_TRANSACTION_TOPIC,
    ):
        if topic not in DOWNSTREAM_HTTP_TOPICS:
            raise ValueError(
                "topic must be one of the configured HTTP transaction topics"
            )
        self.topic = topic
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SUBSCRIBE, topic)
        self.socket.connect(endpoint)

    def receive(self, timeout_ms: int = 3000) -> dict | None:
        """Receive one event, or return None if the timeout expires."""
        if not self.socket.poll(timeout_ms, zmq.POLLIN):
            return None

        topic, payload = self.socket.recv_multipart()
        if topic != self.topic:
            return None
        return json.loads(payload.decode("utf-8"))

    def close(self) -> None:
        """Close the subscriber socket."""
        self.socket.close()
