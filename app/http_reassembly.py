
from dataclasses import dataclass, field


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


class HTTPStreamParser:
    """Parse HTTP/1.x requests and responses from ordered byte chunks."""

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

    def feed(self, data: bytes) -> list[HTTPMessage]:
        """Buffer bytes and return all complete HTTP messages."""
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")

        self.buffer.extend(data)
        messages = []

        while True:
            header_end = self.buffer.find(b"\r\n\r\n")

            if header_end == -1:
                if len(self.buffer) > self.max_header_bytes:
                    self.buffer.clear()
                    raise ValueError("HTTP headers exceed size limit")
                break

            if header_end > self.max_header_bytes:
                self.buffer.clear()
                raise ValueError("HTTP headers exceed size limit")

            header_block = bytes(self.buffer[:header_end])
            header_text = header_block.decode("iso-8859-1")
            lines = header_text.split("\r\n")

            if not lines or not lines[0]:
                self.buffer.clear()
                raise ValueError("Missing HTTP start line")

            start_parts = lines[0].split()

            # Response status line: HTTP/1.1 200 OK
            if start_parts and start_parts[0].startswith("HTTP/1."):
                if len(start_parts) < 2:
                    self.buffer.clear()
                    raise ValueError("Invalid HTTP response status line")

                version = start_parts[0]
                try:
                    status_code = int(start_parts[1])
                except ValueError as exc:
                    self.buffer.clear()
                    raise ValueError("Invalid HTTP response status code") from exc

                if not 100 <= status_code <= 599:
                    self.buffer.clear()
                    raise ValueError("HTTP response status code out of range")

                reason_phrase = " ".join(start_parts[2:])
                message_type = "response"
                method = None
                uri = None
            else:
                if (
                    len(start_parts) != 3
                    or not start_parts[2].startswith("HTTP/1.")
                ):
                    self.buffer.clear()
                    raise ValueError("Invalid HTTP request line")

                method, uri, version = start_parts
                status_code = None
                reason_phrase = None
                message_type = "request"

            headers = {}

            for line in lines[1:]:
                if ":" not in line:
                    self.buffer.clear()
                    raise ValueError("Invalid HTTP header")

                name, value = line.split(":", 1)
                name = name.strip().lower()
                value = value.strip()

                if not name:
                    self.buffer.clear()
                    raise ValueError("Empty HTTP header name")

                if name in headers:
                    self.buffer.clear()
                    raise ValueError(f"Duplicate HTTP header: {name}")

                headers[name] = value

            # This version deliberately rejects chunked framing.
            if "transfer-encoding" in headers:
                self.buffer.clear()
                raise ValueError("Transfer-Encoding is not supported yet")

            content_length = headers.get("content-length", "0")

            # Content-Length must contain only decimal digits.
            if not content_length.isascii() or not content_length.isdecimal():
                self.buffer.clear()
                raise ValueError("Invalid Content-Length")

            body_length = int(content_length)

            if body_length > self.max_body_bytes:
                self.buffer.clear()
                raise ValueError("HTTP body exceeds size limit")

            message_end = header_end + 4 + body_length

            if len(self.buffer) < message_end:
                break

            body = bytes(self.buffer[header_end + 4:message_end])

            messages.append(
                HTTPMessage(
                    version=version,
                    headers=headers,
                    body=body,
                    message_type=message_type,
                    method=method,
                    uri=uri,
                    status_code=status_code,
                    reason_phrase=reason_phrase,
                )
            )

            del self.buffer[:message_end]

        return messages
