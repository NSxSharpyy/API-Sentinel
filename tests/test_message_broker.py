from unittest.mock import Mock
import pytest
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

def test_pipeline_correlates_request_and_reverse_direction_response():
    publisher = __import__("unittest.mock", fromlist=["Mock"]).Mock()
    pipeline = HTTPMessagePipeline(publisher)

    request = (
        b"GET /health HTTP/1.1\r\n"
        b"Host: example.test\r\n\r\n"
    )
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: 2\r\n\r\nOK"
    )

    pipeline.feed(
        request,
        connection_id="TCP|10.0.0.10:49152->10.0.0.20:80",
    )
    pipeline.feed(
        response,
        connection_id="TCP|10.0.0.20:80->10.0.0.10:49152",
    )

    assert len(pipeline.completed_transactions) == 1

    transaction = pipeline.completed_transactions[0]
    assert transaction.request.uri == "/health"
    assert transaction.response.status_code == 200

    # Existing message-by-message publishing remains intact.
    assert publisher.publish.call_count == 2


def test_pipeline_discards_pending_request_when_connection_closes():
    publisher = __import__("unittest.mock", fromlist=["Mock"]).Mock()
    pipeline = HTTPMessagePipeline(publisher)

    connection_id = "TCP|10.0.0.10:49152->10.0.0.20:80"

    pipeline.feed(
        b"GET /pending HTTP/1.1\r\nHost: example.test\r\n\r\n",
        connection_id=connection_id,
    )

    assert pipeline.correlator.pending_request_count == 1

    pipeline.close_connection(
        "TCP|10.0.0.20:80->10.0.0.10:49152"
    )

    assert pipeline.correlator.pending_request_count == 0
    assert pipeline.correlator.dropped_requests == 1


def test_pipeline_persists_correlated_transaction():
    publisher = Mock()
    store = Mock()
    pipeline = HTTPMessagePipeline(
        publisher=publisher,
        transaction_store=store,
    )

    client_to_server = (
        "TCP|10.0.0.10:49152->10.0.0.20:80"
    )
    server_to_client = (
        "TCP|10.0.0.20:80->10.0.0.10:49152"
    )

    pipeline.feed(
        b"GET /health HTTP/1.1\r\nHost: example.test\r\n\r\n",
        connection_id=client_to_server,
    )
    pipeline.feed(
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK",
        connection_id=server_to_client,
    )

    store.save.assert_called_once()
    transaction = store.save.call_args.args[0]
    assert transaction.request.uri == "/health"
    assert transaction.response.status_code == 200
    assert len(pipeline.completed_transactions) == 1
    assert publisher.publish.call_count == 2

def test_pipeline_queues_correlated_transaction_for_background_persistence():
    publisher = Mock()
    store = Mock()

    from app.persistence_worker import TransactionPersistenceWorker

    persistence_worker = TransactionPersistenceWorker(store=store)
    pipeline = HTTPMessagePipeline(
        publisher=publisher,
        persistence_worker=persistence_worker,
    )

    client_to_server = "TCP|10.0.0.10:49152->10.0.0.20:80"
    server_to_client = "TCP|10.0.0.20:80->10.0.0.10:49152"

    pipeline.feed(
        b"GET /health HTTP/1.1\r\nHost: example.test\r\n\r\n",
        connection_id=client_to_server,
    )
    pipeline.feed(
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK",
        connection_id=server_to_client,
    )

    assert persistence_worker.queue.qsize() == 1
    assert store.save.call_count == 0
    assert len(pipeline.completed_transactions) == 1
    assert publisher.publish.call_count == 2

    job = persistence_worker.queue.get_nowait()
    assert job.transaction.request.uri == "/health"
    assert job.transaction.response.status_code == 200
    persistence_worker.queue.task_done()

def test_pipeline_continues_publishing_when_persistence_fails(caplog):
    publisher = Mock()
    store = Mock()
    store.save.side_effect = RuntimeError("database unavailable")

    pipeline = HTTPMessagePipeline(
        publisher=publisher,
        transaction_store=store,
    )

    client_to_server = "TCP|10.0.0.10:49152->10.0.0.20:80"
    server_to_client = "TCP|10.0.0.20:80->10.0.0.10:49152"

    pipeline.feed(
        b"GET /health HTTP/1.1\r\nHost: example.test\r\n\r\n",
        connection_id=client_to_server,
    )
    pipeline.feed(
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK",
        connection_id=server_to_client,
    )

    assert store.save.call_count == 1
    assert publisher.publish.call_count == 2
    assert len(pipeline.completed_transactions) == 1
    assert "Failed to persist HTTP transaction" in caplog.text
def test_pipeline_rejects_new_connection_at_limit():
    publisher = Mock()
    pipeline = HTTPMessagePipeline(publisher, max_connections=2)

    # The default parser already occupies one slot.
    pipeline.feed(b"", connection_id="connection-1")

    assert pipeline.open_connections == 2

    with pytest.raises(
        RuntimeError,
        match="Maximum number of HTTP connections reached",
    ):
        pipeline.feed(b"", connection_id="connection-2")

    assert pipeline.open_connections == 2
    assert "connection-2" not in pipeline._parsers


def test_pipeline_allows_existing_connection_at_limit():
    publisher = Mock()
    pipeline = HTTPMessagePipeline(publisher, max_connections=2)

    pipeline.feed(b"", connection_id="connection-1")
    assert pipeline.open_connections == 2

    # Reusing an existing connection must not consume another slot.
    pipeline.feed(b"", connection_id="connection-1")

    assert pipeline.open_connections == 2
