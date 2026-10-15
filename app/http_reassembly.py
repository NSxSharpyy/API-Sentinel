import re
from dataclasses import dataclass, field


_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_TOKEN_BYTES_RE = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_METHOD_RE = re.compile(r"^[A-Z][A-Z0-9_-]*$")
_MAX_CONTENT_LENGTH_DIGITS = 18

_SINGLETON_HEADERS = {
    "content-length",
    "host",
    "transfer-encoding",
    "content-type",
}


@dataclass
class HTTPMessage:
    """A parsed HTTP/1.x request or response."""

    version: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    message_type: str = "request"
    method: str | None = None
    uri: str | None = None
    status_code: int | None = None
    reason_phrase: str | None = None
    connection_id: str | None = None


class HTTPParseError(ValueError):
    """Parsing error that preserves messages completed before the error."""

    def __init__(
        self,
        message: str,
        messages: list[HTTPMessage] | None = None,
    ):
        super().__init__(message)
        self.messages = messages or []


def _decode_chunked_body(
    data: bytearray,
    start: int,
    max_body_bytes: int,
) -> tuple[bytes, int] | None:
    """Decode a complete chunked body.

    Return (decoded_body, end_offset), or None when more bytes are needed.
    Raise ValueError for malformed chunk framing or oversized bodies.
    """
    pos = start
    decoded = bytearray()

    while True:
        line_end = data.find(b"\r\n", pos)
        if line_end < 0:
            if len(data) - pos > 128:
                raise ValueError("Invalid chunk size line")
            return None

        size_line = bytes(data[pos:line_end])
        size_token = size_line.split(b";", 1)[0]
        if not size_token or any(
            byte not in b"0123456789abcdefABCDEF"
            for byte in size_token
        ):
            raise ValueError("Invalid chunk size")
        if len(size_token) > 16:
            raise ValueError("Invalid chunk size")

        chunk_size = int(size_token, 16)
        pos = line_end + 2

        if chunk_size == 0:
            # An empty trailer section ends with one CRLF.
            if len(data) >= pos + 2 and data[pos:pos + 2] == b"\r\n":
                return bytes(decoded), pos + 2

            trailer_end = data.find(b"\r\n\r\n", pos)
            if trailer_end < 0:
                if len(data) - pos > 65536:
                    raise ValueError("Chunk trailers exceed size limit")
                return None

            trailer_block = bytes(data[pos:trailer_end])
            for line in trailer_block.split(b"\r\n"):
                if (
                    not line
                    or line[:1] in (b" ", b"\t")
                    or b":" not in line
                ):
                    raise ValueError("Invalid chunk trailer")
                name, value = line.split(b":", 1)
                if not _TOKEN_BYTES_RE.fullmatch(name):
                    raise ValueError("Invalid chunk trailer")
                if any(byte < 32 and byte != 9 for byte in value) or b"\x7f" in value:
                    raise ValueError("Invalid chunk trailer")

            return bytes(decoded), trailer_end + 4

        if len(decoded) + chunk_size > max_body_bytes:
            raise ValueError("HTTP body exceeds size limit")

        chunk_end = pos + chunk_size
        if len(data) < chunk_end + 2:
            return None
        if data[chunk_end:chunk_end + 2] != b"\r\n":
            raise ValueError("Invalid chunk data terminator")

        decoded.extend(data[pos:chunk_end])
        pos = chunk_end + 2


class HTTPStreamParser:
    """Parse HTTP/1.x messages from ordered byte chunks."""

    def __init__(
        self,
        max_header_bytes: int = 65536,
        max_body_bytes: int = 10 * 1024 * 1024,
    ):
        if max_header_bytes <= 0:
            raise ValueError("max_header_bytes must be positive")
        if max_body_bytes < 0:
            raise ValueError("max_body_bytes cannot be negative")

        self.buffer = bytearray()
        self.max_header_bytes = max_header_bytes
        self.max_body_bytes = max_body_bytes
        self.pending_head_responses = 0

    def expect_head_response(self) -> None:
        """Mark that the next corresponding response is for a HEAD request."""
        self.pending_head_responses += 1

    def _fail(
        self,
        message: str,
        messages: list[HTTPMessage],
    ) -> None:
        """Clear malformed buffered data and preserve completed messages."""
        self.buffer.clear()
        raise HTTPParseError(message, messages)

    def feed(self, data: bytes) -> list[HTTPMessage]:
        """Buffer bytes and return all complete HTTP messages."""
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")

        self.buffer.extend(data)
        messages: list[HTTPMessage] = []

        while True:
            while self.buffer.startswith(b"\r\n"):
                del self.buffer[:2]

            header_end = self.buffer.find(b"\r\n\r\n")
            if header_end == -1:
                if b"\n\n" in self.buffer:
                    self._fail("Invalid HTTP line endings", messages)
                if len(self.buffer) > self.max_header_bytes:
                    self._fail("HTTP headers exceed size limit", messages)
                break

            if header_end > self.max_header_bytes:
                self._fail("HTTP headers exceed size limit", messages)

            header_block = bytes(self.buffer[:header_end])
            if (
                b"\n" in header_block.replace(b"\r\n", b"")
                or b"\r" in header_block.replace(b"\r\n", b"")
            ):
                self._fail("Invalid HTTP line endings", messages)

            lines = header_block.decode("iso-8859-1").split("\r\n")
            if not lines or not lines[0]:
                self._fail("Missing HTTP start line", messages)
            start_parts = lines[0].split()
            if not start_parts:
                self._fail("Missing HTTP start line", messages)

            if start_parts[0].startswith("HTTP/1."):
                if len(start_parts) < 2:
                    self._fail("Invalid HTTP response status line", messages)
                version = start_parts[0]
                try:
                    status_code = int(start_parts[1])
                except ValueError:
                    self._fail("Invalid HTTP response status code", messages)
                if (
                    not start_parts[1].isascii()
                    or not start_parts[1].isdecimal()
                    or not 100 <= status_code <= 599
                ):
                    self._fail(
                        "HTTP response status code out of range or invalid",
                        messages,
                    )
                reason_phrase = " ".join(start_parts[2:])
                message_type = "response"
                method = None
                uri = None
            else:
                if (
                    len(start_parts) != 3
                    or not start_parts[2].startswith("HTTP/1.")
                ):
                    self._fail("Invalid HTTP request line", messages)
                method, uri, version = start_parts
                if not _METHOD_RE.fullmatch(method):
                    self._fail("Invalid HTTP method", messages)
                if not uri or any(ord(char) <= 32 for char in uri):
                    self._fail("Invalid HTTP request URI", messages)
                status_code = None
                reason_phrase = None
                message_type = "request"

            headers: dict[str, str] = {}
            for line in lines[1:]:
                if not line or line[0] in " \t" or ":" not in line:
                    self._fail("Invalid HTTP header", messages)
                raw_name, value = line.split(":", 1)
                if not _TOKEN_RE.fullmatch(raw_name):
                    self._fail("Invalid HTTP header name", messages)
                name = raw_name.lower()
                value = value.strip(" \t")
                if any(
                    ord(char) < 32 and char != "\t"
                    for char in value
                ) or "\x7f" in value:
                    self._fail("Invalid HTTP header value", messages)
                if name in headers:
                    if name in _SINGLETON_HEADERS:
                        self._fail(f"Duplicate HTTP header: {name}", messages)
                    headers[name] += ", " + value
                else:
                    headers[name] = value

            has_transfer_encoding = "transfer-encoding" in headers
            has_content_length = "content-length" in headers
            if has_transfer_encoding and has_content_length:
                self._fail(
                    "Both Transfer-Encoding and Content-Length are present",
                    messages,
                )

            transfer_encoding = headers.get("transfer-encoding", "").lower()
            if has_transfer_encoding and transfer_encoding != "chunked":
                self._fail("Unsupported Transfer-Encoding", messages)

            content_length = headers.get("content-length", "0")
            if (
                not content_length
                or len(content_length) > _MAX_CONTENT_LENGTH_DIGITS
                or not content_length.isascii()
                or not content_length.isdecimal()
            ):
                self._fail("Invalid Content-Length", messages)

            body_length = int(content_length)
            if body_length > self.max_body_bytes:
                self._fail("HTTP body exceeds size limit", messages)

            bodyless_response = False
            if message_type == "response":
                bodyless_response = (
                    status_code < 200 or status_code in (204, 304)
                )
                if self.pending_head_responses > 0:
                    bodyless_response = True
                    self.pending_head_responses -= 1

            body_start = header_end + 4
            if bodyless_response:
                body = b""
                message_end = body_start
            elif has_transfer_encoding:
                try:
                    decoded = _decode_chunked_body(
                        self.buffer,
                        body_start,
                        self.max_body_bytes,
                    )
                except ValueError as exc:
                    self._fail(str(exc), messages)
                if decoded is None:
                    break
                body, message_end = decoded
            else:
                message_end = body_start + body_length
                if len(self.buffer) < message_end:
                    break
                body = bytes(self.buffer[body_start:message_end])

            message = HTTPMessage(
                version=version,
                headers=headers,
                body=body,
                message_type=message_type,
                method=method,
                uri=uri,
                status_code=status_code,
                reason_phrase=reason_phrase,
            )
            messages.append(message)
            del self.buffer[:message_end]

            if message_type == "request" and method == "HEAD":
                self.expect_head_response()

        return messages
