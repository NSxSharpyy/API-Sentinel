
from collections import deque
from collections.abc import Callable

from app.http_reassembly import (
    HTTPMessage,
    HTTPParseError,
    HTTPStreamParser,
)
from app.message_broker import HTTPTransactionPublisher
from app.transaction_correlator import (
    HTTPTransaction,
    HTTPTransactionCorrelator,
)

DEFAULT_CONNECTION_ID = "default"
MAX_COMPLETED_TRANSACTIONS = 1000


class HTTPMessagePipeline:
    """Parse HTTP messages, publish events, and correlate transactions."""

    def __init__(
        self,
        publisher: HTTPTransactionPublisher,
        parser: HTTPStreamParser | None = None,
        parser_factory: Callable[[], HTTPStreamParser] = HTTPStreamParser,
        max_connections: int = 10000,
        correlator: HTTPTransactionCorrelator | None = None,
    ):
        if max_connections <= 0:
            raise ValueError("max_connections must be positive")

        self.publisher = publisher
        self.parser_factory = parser_factory
        self.max_connections = max_connections
        self.correlator = (
            correlator
            if correlator is not None
            else HTTPTransactionCorrelator()
        )

        # Retain only the latest transactions for inspection.
        self.completed_transactions: deque[HTTPTransaction] = deque(
            maxlen=MAX_COMPLETED_TRANSACTIONS
        )

        # Preserve compatibility with callers using the default parser.
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
        """Return the number of parser instances currently retained."""
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
        """Remove parser state and pending correlation requests."""
        self._parsers.pop(connection_id, None)
        self.correlator.close_connection(connection_id)

    def _publish_all(
        self,
        messages: list[HTTPMessage],
        connection_id: str,
    ) -> None:
        """Correlate completed messages and publish individual events."""
        for message in messages:
            message.connection_id = connection_id

            transaction = self.correlator.process(message)
            if transaction is not None:
                self.completed_transactions.append(transaction)

            # Preserve the existing ZeroMQ per-message event contract.
            self.publisher.publish(message)

    def feed(
        self,
        data: bytes,
        connection_id: str = DEFAULT_CONNECTION_ID,
    ) -> list[HTTPMessage]:
        """Parse, correlate, and publish complete HTTP messages."""
        parser = self._get_parser(connection_id)

        try:
            messages = parser.feed(data)
        except HTTPParseError as exc:
            self._publish_all(exc.messages, connection_id)
            self.close_connection(connection_id)
            raise

        self._publish_all(messages, connection_id)
        return messages
