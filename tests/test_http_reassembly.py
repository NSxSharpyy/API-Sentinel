
import pytest

from app.http_reassembly import HTTPStreamParser


def test_complete_get_request():
    parser = HTTPStreamParser()

    messages = parser.feed(
        b"GET /api/users HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        b"\r\n"
    )

    assert len(messages) == 1
    assert messages[0].method == "GET"
    assert messages[0].uri == "/api/users"
    assert messages[0].headers["host"] == "example.com"
    assert messages[0].body == b""


def test_request_split_across_chunks():
    parser = HTTPStreamParser()

    first = parser.feed(b"GET /api/")
    assert first == []

    second = parser.feed(
        b"users HTTP/1.1\r\nHost: example.com\r\n"
    )
    assert second == []

    third = parser.feed(b"\r\n")
    assert len(third) == 1
    assert third[0].uri == "/api/users"


def test_body_split_across_chunks():
    parser = HTTPStreamParser()

    first = parser.feed(
        b"POST /submit HTTP/1.1\r\n"
        b"Content-Length: 5\r\n\r\nhe"
    )
    assert first == []

    second = parser.feed(b"llo")
    assert len(second) == 1
    assert second[0].body == b"hello"


def test_multiple_requests_in_one_chunk():
    parser = HTTPStreamParser()

    messages = parser.feed(
        b"GET /one HTTP/1.1\r\n\r\n"
        b"GET /two HTTP/1.1\r\n\r\n"
    )

    assert len(messages) == 2
    assert messages[0].uri == "/one"
    assert messages[1].uri == "/two"


def test_rejects_invalid_request_line():
    parser = HTTPStreamParser()

    with pytest.raises(ValueError):
        parser.feed(b"NOT_HTTP\r\n\r\n")


def test_rejects_transfer_encoding_for_now():
    parser = HTTPStreamParser()

    with pytest.raises(ValueError):
        parser.feed(
            b"POST / HTTP/1.1\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
        )


def test_rejects_non_bytes_input():
    parser = HTTPStreamParser()

    with pytest.raises(TypeError):
        parser.feed("GET / HTTP/1.1\r\n\r\n")