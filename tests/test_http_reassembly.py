
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


def test_complete_chunked_http_response():
    parser = HTTPStreamParser()

    messages = parser.feed(
        b"HTTP/1.1 200 OK\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"5\r\nHello\r\n"
        b"6\r\n World\r\n"
        b"0\r\n\r\n"
    )

    assert len(messages) == 1
    assert messages[0].message_type == "response"
    assert messages[0].status_code == 200
    assert messages[0].body == b"Hello World"


def test_chunked_response_split_across_feeds():
    parser = HTTPStreamParser()

    first = parser.feed(
        b"HTTP/1.1 200 OK\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        b"5\r\nHel"
    )
    assert first == []

    second = parser.feed(b"lo\r\n0\r\n\r\n")
    assert len(second) == 1
    assert second[0].body == b"Hello"


def test_chunked_response_preserves_following_response():
    parser = HTTPStreamParser()

    messages = parser.feed(
        b"HTTP/1.1 200 OK\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        b"2\r\nOK\r\n"
        b"0\r\n\r\n"
        b"HTTP/1.1 204 No Content\r\n\r\n"
    )

    assert len(messages) == 2
    assert messages[0].body == b"OK"
    assert messages[1].status_code == 204
    assert messages[1].body == b""


def test_complete_http_response():
    parser = HTTPStreamParser()

    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: 5\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Hello"
    )

    messages = parser.feed(raw)

    assert len(messages) == 1
    response = messages[0]
    assert response.message_type == "response"
    assert response.version == "HTTP/1.1"
    assert response.status_code == 200
    assert response.reason_phrase == "OK"
    assert response.headers["content-length"] == "5"
    assert response.body == b"Hello"
    assert response.method is None
    assert response.uri is None


def test_fragmented_http_response():
    parser = HTTPStreamParser()

    first = parser.feed(
        b"HTTP/1.1 404 Not Found\r\n"
        b"Content-Length: 4\r\n\r\n"
        b"No"
    )
    assert first == []

    second = parser.feed(b"pe")
    assert len(second) == 1
    assert second[0].status_code == 404
    assert second[0].reason_phrase == "Not Found"
    assert second[0].body == b"Nope"


def test_valid_body_within_limit():
    parser = HTTPStreamParser(max_body_bytes=5)

    messages = parser.feed(
        b"POST /test HTTP/1.1\r\n"
        b"Content-Length: 5\r\n\r\n"
        b"12345"
    )

    assert len(messages) == 1
    assert messages[0].body == b"12345"


def test_rejects_body_over_limit():
    parser = HTTPStreamParser(max_body_bytes=4)

    with pytest.raises(ValueError, match="body exceeds size limit"):
        parser.feed(
            b"POST /test HTTP/1.1\r\n"
            b"Content-Length: 5\r\n\r\n"
        )

    assert parser.buffer == bytearray()


def test_rejects_invalid_content_length():
    invalid_values = [b"-1", b"abc", b"+5", b"1.5"]

    for value in invalid_values:
        parser = HTTPStreamParser()
        request = (
            b"POST /test HTTP/1.1\r\n"
            b"Content-Length: "
            + value
            + b"\r\n\r\n"
        )

        with pytest.raises(ValueError, match="Invalid Content-Length"):
            parser.feed(request)

        assert parser.buffer == bytearray()


def test_rejects_response_status_code_out_of_range():
    parser = HTTPStreamParser()

    with pytest.raises(ValueError, match="status code out of range"):
        parser.feed(
            b"HTTP/1.1 999 Invalid\r\n\r\n"
        )

    assert parser.buffer == bytearray()
def test_query_string_is_preserved_in_uri():
    parser = HTTPStreamParser()

    messages = parser.feed(
        b"GET /api/users?role=admin&page=2 HTTP/1.1\r\n"
        b"Host: example.com\r\n\r\n"
    )

    assert len(messages) == 1
    assert messages[0].uri == "/api/users?role=admin&page=2"


def test_chunked_request_with_trailers():
    parser = HTTPStreamParser()

    messages = parser.feed(
        b"POST /upload?source=test HTTP/1.1\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        b"4\r\nWiki\r\n"
        b"5\r\npedia\r\n"
        b"0\r\n"
        b"X-Checksum: abc123\r\n"
        b"\r\n"
    )

    assert len(messages) == 1
    assert messages[0].uri == "/upload?source=test"
    assert messages[0].body == b"Wikipedia"


def test_multipart_form_body_is_preserved():
    parser = HTTPStreamParser()
    boundary = b"----Boundary123"

    body = (
        b"------Boundary123\r\n"
        b'Content-Disposition: form-data; name="username"\r\n\r\n'
        b"harsha\r\n"
        b"------Boundary123\r\n"
        b'Content-Disposition: form-data; name="note"\r\n\r\n'
        b"hello world\r\n"
        b"------Boundary123--\r\n"
    )

    request = (
        b"POST /upload HTTP/1.1\r\n"
        b"Content-Type: multipart/form-data; boundary="
        + boundary
        + b"\r\n"
        + b"Content-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )

    messages = parser.feed(request)

    assert len(messages) == 1
    assert messages[0].headers["content-type"] == (
        "multipart/form-data; boundary=----Boundary123"
    )
    assert messages[0].body == body


def test_rejects_malformed_chunk_terminator():
    parser = HTTPStreamParser()

    with pytest.raises(ValueError, match="Invalid chunk data terminator"):
        parser.feed(
            b"POST /upload HTTP/1.1\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"3\r\nabcXX"
        )
