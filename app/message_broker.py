

import base64
import json
from datetime import timezone

import zmq

from app.http_reassembly import HTTPMessage

HTTP_TRANSACTION_TOPIC = b"http.transaction"


def serialize_http_message(message: HTTPMessage) -> bytes:
    """Serialize an HTTP request or response into a JSON broker event."""
    event = {
        "event_type": "http.transaction",
        "message_type": message.message_type,
        "connection_id": message.connection_id,
        "captured_at": (
            message.captured_at.astimezone(timezone.utc).isoformat()
            if message.captured_at is not None
            else None
        ),
        "method": message.method,
        "uri": message.uri,
        "status_code": message.status_code,
        "reason_phrase": message.reason_phrase,
        "version": message.version,
        "headers": message.headers,
        "body_base64": base64.b64encode(message.body).decode("ascii"),
    }

    return json.dumps(event, separators=(",", ":")).encode("utf-8")


class HTTPTransactionPublisher:
    """Publish HTTP transaction events through a ZeroMQ PUB socket."""

    def __init__(self, endpoint: str = "tcp://127.0.0.1:5557"):
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.bind(endpoint)

    def publish(self, message: HTTPMessage) -> None:
        """Publish one HTTP message on the transaction topic."""
        payload = serialize_http_message(message)
        self.socket.send_multipart(
            [HTTP_TRANSACTION_TOPIC, payload]
        )

    def close(self) -> None:
        """Close the publisher socket."""
        self.socket.close()


class HTTPTransactionSubscriber:
    """Receive HTTP transaction events from a ZeroMQ PUB socket."""

    def __init__(self, endpoint: str = "tcp://127.0.0.1:5557"):
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(
            zmq.SUBSCRIBE,
            HTTP_TRANSACTION_TOPIC,
        )
        self.socket.connect(endpoint)

    def receive(self, timeout_ms: int = 3000) -> dict | None:
        """Receive one event, or return None if the timeout expires."""
        if not self.socket.poll(timeout_ms, zmq.POLLIN):
            return None

        topic, payload = self.socket.recv_multipart()

        if topic != HTTP_TRANSACTION_TOPIC:
            return None

        return json.loads(payload.decode("utf-8"))

    def close(self) -> None:
        """Close the subscriber socket."""
        self.socket.close()
