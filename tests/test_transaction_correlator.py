
from time import monotonic

from app.http_reassembly import HTTPMessage
from app.transaction_correlator import HTTPTransactionCorrelator


CLIENT_TO_SERVER = "TCP|10.0.0.10:49152->10.0.0.20:80"
SERVER_TO_CLIENT = "TCP|10.0.0.20:80->10.0.0.10:49152"


def make_message(message_type, connection_id, **kwargs):
    return HTTPMessage(
        version="HTTP/1.1",
        message_type=message_type,
        connection_id=connection_id,
        **kwargs,
    )


def test_matches_request_and_reverse_direction_response():
    correlator = HTTPTransactionCorrelator()

    request = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/health"
    )
    response = make_message(
        "response", SERVER_TO_CLIENT, status_code=200
    )

    assert correlator.process(request) is None
    transaction = correlator.process(response)

    assert transaction is not None
    assert transaction.request.uri == "/health"
    assert transaction.response.status_code == 200
    assert correlator.pending_request_count == 0



def test_switching_protocols_response_consumes_pending_request():
    correlator = HTTPTransactionCorrelator()
    request = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/ws"
    )
    interim = make_message(
        "response", SERVER_TO_CLIENT, status_code=100
    )
    switching = make_message(
        "response", SERVER_TO_CLIENT, status_code=101
    )

    assert correlator.process(request) is None
    assert correlator.process(interim) is None
    assert correlator.pending_request_count == 1

    transaction = correlator.process(switching)

    assert transaction is not None
    assert transaction.request.uri == "/ws"
    assert transaction.response.status_code == 101
    assert correlator.pending_request_count == 0

def test_does_not_match_different_connections():
    correlator = HTTPTransactionCorrelator()

    request = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/one"
    )
    response = make_message(
        "response",
        "TCP|10.0.0.30:80->10.0.0.40:49153",
        status_code=200,
    )

    correlator.process(request)

    assert correlator.process(response) is None
    assert correlator.pending_request_count == 1
    assert correlator.unmatched_responses == 1


def test_matches_multiple_requests_in_fifo_order():
    correlator = HTTPTransactionCorrelator()

    first = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/first"
    )
    second = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/second"
    )
    response_one = make_message(
        "response", SERVER_TO_CLIENT, status_code=200
    )
    response_two = make_message(
        "response", SERVER_TO_CLIENT, status_code=404
    )

    correlator.process(first)
    correlator.process(second)

    result_one = correlator.process(response_one)
    result_two = correlator.process(response_two)

    assert result_one is not None
    assert result_two is not None
    assert result_one.request.uri == "/first"
    assert result_two.request.uri == "/second"
    assert result_two.response.status_code == 404


def test_unmatched_response_is_counted():
    correlator = HTTPTransactionCorrelator()

    response = make_message(
        "response", SERVER_TO_CLIENT, status_code=500
    )

    assert correlator.process(response) is None
    assert correlator.unmatched_responses == 1


def test_close_connection_discards_pending_requests():
    correlator = HTTPTransactionCorrelator()

    request = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/pending"
    )
    correlator.process(request)

    correlator.close_connection(CLIENT_TO_SERVER)

    assert correlator.pending_request_count == 0
    assert correlator.dropped_requests == 1


def test_reverse_direction_closes_same_connection():
    correlator = HTTPTransactionCorrelator()

    request = make_message(
        "request", CLIENT_TO_SERVER, method="GET", uri="/pending"
    )
    correlator.process(request)

    correlator.close_connection(SERVER_TO_CLIENT)

    assert correlator.pending_request_count == 0
    assert correlator.dropped_requests == 1


def test_pending_count_for_connection_works_in_both_directions():
    correlator = HTTPTransactionCorrelator()

    correlator.process(
        make_message(
            "request", CLIENT_TO_SERVER, method="GET", uri="/one"
        )
    )

    assert correlator.pending_for_connection(CLIENT_TO_SERVER) == 1
    assert correlator.pending_for_connection(SERVER_TO_CLIENT) == 1

def test_expired_requests_have_a_separate_drop_counter():
    correlator = HTTPTransactionCorrelator(request_ttl_seconds=1.0)
    correlator.process(
        make_message(
            "request", CLIENT_TO_SERVER, method="GET", uri="/expires"
        )
    )

    expired = correlator.expire_stale_requests(now=monotonic() + 2.0)

    assert expired == 1
    assert correlator.expired_requests == 1
    assert correlator.capacity_evicted_requests == 0
    assert correlator.connection_closed_requests == 0
    assert correlator.dropped_requests == 1


def test_capacity_evictions_have_a_separate_drop_counter():
    correlator = HTTPTransactionCorrelator(max_pending_per_connection=1)

    correlator.process(
        make_message(
            "request", CLIENT_TO_SERVER, method="GET", uri="/first"
        )
    )
    correlator.process(
        make_message(
            "request", CLIENT_TO_SERVER, method="GET", uri="/second"
        )
    )

    assert correlator.pending_request_count == 1
    assert correlator.expired_requests == 0
    assert correlator.capacity_evicted_requests == 1
    assert correlator.connection_closed_requests == 0
    assert correlator.dropped_requests == 1


def test_connection_closures_have_a_separate_drop_counter():
    correlator = HTTPTransactionCorrelator()
    correlator.process(
        make_message(
            "request", CLIENT_TO_SERVER, method="GET", uri="/close"
        )
    )

    correlator.close_connection(CLIENT_TO_SERVER)

    assert correlator.pending_request_count == 0
    assert correlator.expired_requests == 0
    assert correlator.capacity_evicted_requests == 0
    assert correlator.connection_closed_requests == 1
    assert correlator.dropped_requests == 1

def test_drop_diagnostic_excludes_request_and_connection_identifiers():
    correlator = HTTPTransactionCorrelator()
    correlator.process(
        make_message(
            "request",
            CLIENT_TO_SERVER,
            method="GET",
            uri="/admin?access_token=do-not-record",
        )
    )

    correlator.close_connection(CLIENT_TO_SERVER, reason="tcp_rst")

    assert correlator.drop_reason_counts == {"tcp_rst": 1}
    assert len(correlator.recent_drop_samples) == 1

    sample = correlator.recent_drop_samples[0]
    assert sample["reason"] == "tcp_rst"
    assert sample["method"] == "GET"
    assert isinstance(sample["age_seconds"], float)
    assert sample["age_seconds"] >= 0
    assert set(sample) == {"reason", "method", "age_seconds"}
    assert "/admin" not in str(sample)
    assert "access_token" not in str(sample)
    assert "do-not-record" not in str(sample)
    assert CLIENT_TO_SERVER not in str(sample)
