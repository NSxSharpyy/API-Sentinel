import socket
from unittest.mock import Mock

import pytest
import zmq

from app import queues
from app.message_broker import HTTPTransactionPublisher, HTTPTransactionSubscriber
from app.persistence_worker import TransactionPersistenceWorker


def available_endpoint():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"tcp://127.0.0.1:{port}"


def test_all_application_queues_have_finite_positive_capacity():
    for q in (
        queues.raw_packet_queue,
        queues.header_queue,
        queues.metadata_queue,
        queues.blocklist_verdict_queue,
    ):
        assert q.maxsize > 0


@pytest.mark.parametrize("bad_value", ["0", "-1", "invalid"])
def test_queue_capacity_parser_rejects_invalid_values(monkeypatch, bad_value):
    monkeypatch.setenv("API_SENTINEL_TEST_CAPACITY", bad_value)
    with pytest.raises(ValueError, match="positive integer"):
        queues._positive_int_env("API_SENTINEL_TEST_CAPACITY", 10)


def test_persistence_queue_is_bounded_and_counts_rejections():
    worker = TransactionPersistenceWorker(
        store=Mock(), max_queue_size=2, batch_max_size=1
    )
    assert worker.enqueue(object())
    assert worker.enqueue(object())
    assert not worker.enqueue(object())
    assert worker.queue.qsize() == 2
    assert worker.max_queue_depth == 2
    assert worker.rejected_count == 1


@pytest.mark.parametrize("batch_size", [0, -1])
def test_persistence_batch_size_must_be_positive(batch_size):
    with pytest.raises(ValueError, match="batch_max_size must be positive"):
        TransactionPersistenceWorker(
            store=Mock(), max_queue_size=2, batch_max_size=batch_size
        )


def test_publisher_uses_configured_send_hwm(monkeypatch):
    monkeypatch.setenv("API_SENTINEL_ZMQ_SNDHWM", "64")
    publisher = HTTPTransactionPublisher(available_endpoint())
    try:
        assert publisher.socket.getsockopt(zmq.SNDHWM) == 64
    finally:
        publisher.close()


def test_subscriber_uses_configured_receive_hwm(monkeypatch):
    monkeypatch.setenv("API_SENTINEL_ZMQ_RCVHWM", "48")
    subscriber = HTTPTransactionSubscriber(available_endpoint())
    try:
        assert subscriber.socket.getsockopt(zmq.RCVHWM) == 48
    finally:
        subscriber.close()
