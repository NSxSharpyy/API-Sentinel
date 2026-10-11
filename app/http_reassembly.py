
from dataclasses import dataclass, field


@dataclass
class HTTPMessage:
    method: str
    uri: str
    version: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


class HTTPStreamParser:
    """Parse HTTP/1.x requests from ordered byte chunks."""

    def __init__(self, max_header_bytes: int = 65536):
        self.buffer = bytearray()
        self.max_header_bytes = max_header_bytes

    def feed(self, data: bytes) -> list[HTTPMessage]:
        """Add bytes and return every complete HTTP request."""
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

            try:
                header_text = header_block.decode("iso-8859-1")
            except UnicodeDecodeError as exc:
                raise ValueError("Invalid HTTP headers") from exc

            lines = header_text.split("\r\n")
            request_line = lines[0].split()

            if (
                len(request_line) != 3
                or not request_line[2].startswith("HTTP/1.")
            ):
                self.buffer.clear()
                raise ValueError("Invalid HTTP request line")

            method, uri, version = request_line
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
                    raise ValueError(
                        f"Duplicate HTTP header: {name}"
                    )

                headers[name] = value

            # Avoid ambiguous message framing in this first version.
            if "transfer-encoding" in headers:
                self.buffer.clear()
                raise ValueError(
                    "Transfer-Encoding is not supported yet"
                )

            content_length = headers.get("content-length", "0")

            try:
                body_length = int(content_length)
            except ValueError as exc:
                self.buffer.clear()
                raise ValueError("Invalid Content-Length") from exc

            if body_length < 0:
                self.buffer.clear()
                raise ValueError("Negative Content-Length")

            message_end = header_end + 4 + body_length

            if len(self.buffer) < message_end:
                break

            body = bytes(self.buffer[header_end + 4:message_end])

            messages.append(
                HTTPMessage(
                    method=method,
                    uri=uri,
                    version=version,
                    headers=headers,
                    body=body,
                )
            )

            del self.buffer[:message_end]

        return messages
