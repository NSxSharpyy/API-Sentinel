from unittest.mock import Mock

from app.http_pipeline import HTTPMessagePipeline


def test_head_response_uses_reverse_direction_context_and_preserves_next_response():
    publisher = Mock()
    pipeline = HTTPMessagePipeline(publisher)
    request_direction = "TCP|10.0.0.10:49152->10.0.0.20:80"
    response_direction = "TCP|10.0.0.20:80->10.0.0.10:49152"

    requests = pipeline.feed(
        b"HEAD /metadata HTTP/1.1\r\nHost: example.test\r\n\r\n"
        b"GET /body HTTP/1.1\r\nHost: example.test\r\n\r\n",
        connection_id=request_direction,
    )
    assert [message.method for message in requests] == ["HEAD", "GET"]

    # HEAD responses may advertise the corresponding GET length, but have no
    # body on the wire. The next response must remain aligned in the stream.
    responses = pipeline.feed(
        b"HTTP/1.1 200 OK\r\nContent-Length: 999\r\n\r\n"
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK",
        connection_id=response_direction,
    )

    assert len(responses) == 2
    assert responses[0].body == b""
    assert responses[1].body == b"OK"
    assert len(pipeline.completed_transactions) == 2
    assert pipeline.completed_transactions[0].request.method == "HEAD"
    assert pipeline.completed_transactions[0].response.body == b""
    assert pipeline.completed_transactions[1].request.method == "GET"
    assert pipeline.completed_transactions[1].response.body == b"OK"
    assert pipeline.correlator.unmatched_responses == 0


def test_interim_100_response_does_not_consume_head_context_or_request_pair():
    publisher = Mock()
    pipeline = HTTPMessagePipeline(publisher)
    request_direction = "TCP|10.0.0.10:49152->10.0.0.20:80"
    response_direction = "TCP|10.0.0.20:80->10.0.0.10:49152"

    pipeline.feed(
        b"HEAD /metadata HTTP/1.1\r\nHost: example.test\r\n\r\n"
        b"GET /body HTTP/1.1\r\nHost: example.test\r\n\r\n",
        connection_id=request_direction,
    )
    responses = pipeline.feed(
        b"HTTP/1.1 100 Continue\r\n\r\n"
        b"HTTP/1.1 200 OK\r\nContent-Length: 999\r\n\r\n"
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK",
        connection_id=response_direction,
    )

    assert [response.status_code for response in responses] == [100, 200, 200]
    assert [response.body for response in responses] == [b"", b"", b"OK"]
    assert len(pipeline.completed_transactions) == 2
    assert pipeline.completed_transactions[0].request.method == "HEAD"
    assert pipeline.completed_transactions[0].response.status_code == 200
    assert pipeline.completed_transactions[1].request.method == "GET"
    assert pipeline.completed_transactions[1].response.body == b"OK"
    assert pipeline.correlator.unmatched_responses == 0
