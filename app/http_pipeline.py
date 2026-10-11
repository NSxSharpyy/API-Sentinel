
from collections.abc import Callable

from app.http_reassembly import (
    HTTPMessage,
    HTTPParseError,
    HTTPStreamParser,
)
from app.message_broker import HTTPTransactionPublisher

DEFAULT_CONNECTION_ID = "default"


class HTTPMessagePipeline:
    """Parse HTTP byte chunks and publish completed messages per connection."""

    def __init__(
        self,
        publisher: HTTPTransactionPublisher,
        parser: HTTPStreamParser | None = None,
        parser_factory: Callable[[], HTTPStreamParser] = HTTPStreamParser,
        max_connections: int = 10000,
    ):
        if max_connections <= 0:
            raise ValueError("max_connections must be positive")

        self.publisher = publisher
        self.parser_factory = parser_factory
        self.max_connections = max_connections

        # Preserve compatibility with callers that provide a parser.
        self._parsers: dict[str, HTTPStreamParser] = {
            DEFAULT_CONNECTION_ID: (
                parser if parser is not None else parser_factory()
            )
        }

    @property
    def parser(self) -> HTTPStreamParser:
        """Return the default parser for backwards compatibility."""
        return self._parsers[DEFAULT_CONNECTION_ID]

    @property
    def open_connections(self) -> int:
        """Return the number of connection parsers currently retained."""
        return len(self._parsers)

    def _get_parser(self, connection_id: str) -> HTTPStreamParser:
        """Get or create a parser for a connection."""
        if not isinstance(connection_id, str) or not connection_id:
            raise ValueError("connection_id must be a non-empty string")

        parser = self._parsers.get(connection_id)
        if parser is not None:
            return parser

        if len(self._parsers) >= self.max_connections:
            raise RuntimeError("Maximum number of HTTP connections reached")

        parser = self.parser_factory()
        self._parsers[connection_id] = parser
        return parser

    def close_connection(
        self,
        connection_id: str = DEFAULT_CONNECTION_ID,
    ) -> None:
        """Remove parser state when a connection is closed."""
        self._parsers.pop(connection_id, None)

    def _publish_all(
        self,
        messages: list[HTTPMessage],
        connection_id: str,
    ) -> None:
        """Attach connection identity and publish completed messages."""
        for message in messages:
            message.connection_id = connection_id
            self.publisher.publish(message)

    def feed(
        self,
        data: bytes,
        connection_id: str = DEFAULT_CONNECTION_ID,
    ) -> list[HTTPMessage]:
        """Parse and publish messages for one connection.

        Completed messages are published even if a later message in the
        same input chunk is malformed.
        """
        parser = self._get_parser(connection_id)

        try:
            messages = parser.feed(data)
        except HTTPParseError as exc:
            self._publish_all(exc.messages, connection_id)
            self.close_connection(connection_id)
            raise

        self._publish_all(messages, connection_id)
        return messages
