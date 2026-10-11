
import re
from dataclasses import dataclass, field


_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
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
            # Ignore stray empty lines between messages.
            while self.buffer.startswith(b"\r\n"):
                del self.buffer[:2]

            header_end = self.buffer.find(b"\r\n\r\n")

            if header_end == -1:
                # Reject obvious bare-LF header termination.
                if b"\n\n" in self.buffer:
                    self._fail("Invalid HTTP line endings", messages)

                if len(self.buffer) > self.max_header_bytes:
                    self._fail("HTTP headers exceed size limit", messages)

                break

            if header_end > self.max_header_bytes:
                self._fail("HTTP headers exceed size limit", messages)

            header_block = bytes(self.buffer[:header_end])

            # Header lines must use CRLF, without embedded bare CR or LF.
            if (
                b"\n" in header_block.replace(b"\r\n", b"")
                or b"\r" in header_block.replace(b"\r\n", b"")
            ):
                self._fail("Invalid HTTP line endings", messages)

            header_text = header_block.decode("iso-8859-1")
            lines = header_text.split("\r\n")

            if not lines or not lines[0]:
                self._fail("Missing HTTP start line", messages)

            start_parts = lines[0].split()

            if not start_parts:
                self._fail("Missing HTTP start line", messages)

            # Response status line, for example: HTTP/1.1 200 OK
            if start_parts[0].startswith("HTTP/1."):
                if len(start_parts) < 2:
                    self._fail(
                        "Invalid HTTP response status line",
                        messages,
                    )

                version = start_parts[0]

                try:
                    status_code = int(start_parts[1])
                except ValueError:
                    self._fail(
                        "Invalid HTTP response status code",
                        messages,
                    )

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
                        self._fail(
                            f"Duplicate HTTP header: {name}",
                            messages,
                        )

                    # Preserve repeated headers in a single normalized field.
                    headers[name] += ", " + value
                else:
                    headers[name] = value

            # Reject unsupported transfer framing and ambiguous framing.
            if (
                "transfer-encoding" in headers
                and "content-length" in headers
            ):
                self._fail(
                    "Both Transfer-Encoding and Content-Length are present",
                    messages,
                )

            if "transfer-encoding" in headers:
                self._fail(
                    "Transfer-Encoding is not supported yet",
                    messages,
                )

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
                    status_code < 200
                    or status_code in (204, 304)
                )

                if self.pending_head_responses > 0:
                    bodyless_response = True
                    self.pending_head_responses -= 1

            if bodyless_response:
                body_length = 0

            message_end = header_end + 4 + body_length

            if len(self.buffer) < message_end:
                break

            body = bytes(self.buffer[header_end + 4:message_end])

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
