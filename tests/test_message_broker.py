import socket
import time

from app.message_broker import (
    HTTPTransactionPublisher,
    HTTPTransactionSubscriber,
)
import base64
import json

from app.http_reassembly import HTTPMessage
from app.message_broker import (
    HTTP_TRANSACTION_TOPIC,
    serialize_http_message,
)


def test_serializes_http_request_as_json():
    message = HTTPMessage(
        method="GET",
        uri="/api/users",
        version="HTTP/1.1",
        headers={"host": "example.test"},
        body=b"",
    )

    event = json.loads(serialize_http_message(message))

    assert event["event_type"] == "http.transaction"
    assert event["method"] == "GET"
    assert event["uri"] == "/api/users"
    assert event["version"] == "HTTP/1.1"
    assert event["headers"]["host"] == "example.test"
    assert event["body_base64"] == ""


def test_preserves_binary_request_body():
    original_body = b"\x00\xff\x10hello\x80"

    message = HTTPMessage(
        method="POST",
        uri="/api/upload",
        version="HTTP/1.1",
        headers={"content-type": "application/octet-stream"},
        body=original_body,
    )

    event = json.loads(serialize_http_message(message))
    decoded_body = base64.b64decode(event["body_base64"])

    assert decoded_body == original_body


def test_topic_is_bytes():
    assert HTTP_TRANSACTION_TOPIC == b"http.transaction"

def test_publisher_delivers_http_transaction():
    # Ask Windows for an available local TCP port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    endpoint = f"tcp://127.0.0.1:{port}"
    subscriber = HTTPTransactionSubscriber(endpoint)
    publisher = None

    try:
        # Allow the subscriber to connect and subscribe.
        time.sleep(0.3)
        publisher = HTTPTransactionPublisher(endpoint)
        time.sleep(0.3)

        message = HTTPMessage(
            method="POST",
            uri="/api/events",
            version="HTTP/1.1",
            headers={"content-type": "application/json"},
            body=b'{"event":"test"}',
        )

        publisher.publish(message)
        event = subscriber.receive(timeout_ms=3000)

        assert event is not None
        assert event["event_type"] == "http.transaction"
        assert event["method"] == "POST"
        assert event["uri"] == "/api/events"
        assert event["body_base64"] == "eyJldmVudCI6InRlc3QifQ=="

    finally:
        if publisher is not None:
            publisher.close()
        subscriber.close()

