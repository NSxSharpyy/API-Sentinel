
import base64
import json
import socket
import time
import uuid

from app.http_pipeline import HTTPMessagePipeline
from app.http_reassembly import HTTPMessage
from app.message_broker import (
    HTTP_TRANSACTION_TOPIC,
    HTTPTransactionPublisher,
    HTTPTransactionSubscriber,
    serialize_http_message,
)


def _available_endpoint():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    return f"tcp://127.0.0.1:{port}"


def _wait_for_subscriber(subscriber, publisher, timeout=3.0):
    """Wait until a uniquely identifiable probe event is received."""
    marker = f"readiness-{uuid.uuid4().hex}"
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        message = HTTPMessage(
            method="GET",
            uri=f"/{marker}",
            version="HTTP/1.1",
            headers={},
            body=b"",
        )
        publisher.publish(message)

        event = subscriber.receive(timeout_ms=100)

        if event is not None and event.get("uri") == f"/{marker}":
            return

    raise AssertionError("Subscriber did not receive readiness event in time")


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
    endpoint = _available_endpoint()
    subscriber = HTTPTransactionSubscriber(endpoint)
    publisher = None

    try:
        publisher = HTTPTransactionPublisher(endpoint)
        _wait_for_subscriber(subscriber, publisher)

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


def test_pipeline_publishes_fragmented_http_request():
    endpoint = _available_endpoint()
    subscriber = HTTPTransactionSubscriber(endpoint)
    publisher = None

    try:
        publisher = HTTPTransactionPublisher(endpoint)
        _wait_for_subscriber(subscriber, publisher)

        pipeline = HTTPMessagePipeline(publisher)

        first = pipeline.feed(
            b"POST /api/events HTTP/1.1\r\n"
            b"Host: example.test\r\n"
            b"Content-Length: 7\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"hel"
        )

        assert first == []

        second = pipeline.feed(b"lo!!!")

        assert len(second) == 1
        assert second[0].method == "POST"
        assert second[0].uri == "/api/events"
        assert second[0].body == b"hello!!"

        event = subscriber.receive(timeout_ms=3000)

        assert event is not None
        assert event["event_type"] == "http.transaction"
        assert event["method"] == "POST"
        assert event["uri"] == "/api/events"
        assert event["version"] == "HTTP/1.1"
        assert event["headers"]["host"] == "example.test"
        assert event["body_base64"] == "aGVsbG8hIQ=="

    finally:
        if publisher is not None:
            publisher.close()
        subscriber.close()
