import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone

from app.http_reassembly import (
    HTTPMessage,
    HTTPParseError,
    HTTPStreamParser,
)
from app.message_broker import HTTPTransactionPublisher
from app.persistence_worker import TransactionPersistenceWorker
from app.transaction_correlator import (
    HTTPTransaction,
    HTTPTransactionCorrelator,
)
from app.transaction_store import TransactionStore

logger = logging.getLogger(__name__)

DEFAULT_CONNECTION_ID = "default"
MAX_COMPLETED_TRANSACTIONS = 1000


def _reverse_connection_id(connection_id: str) -> str | None:
    """Return the reverse directional key for a TCP connection ID."""
    if not isinstance(connection_id, str) or "|" not in connection_id:
        return None
    protocol, endpoints = connection_id.split("|", 1)
    if "->" not in endpoints:
        return None
    source, destination = endpoints.split("->", 1)
    if not protocol or not source or not destination:
        return None
    return f"{protocol}|{destination}->{source}"


class HTTPMessagePipeline:
    """Parse HTTP messages, correlate transactions, and persist events."""

    def __init__(
        self,
        publisher: HTTPTransactionPublisher,
        parser: HTTPStreamParser | None = None,
        parser_factory: Callable[[], HTTPStreamParser] = HTTPStreamParser,
        max_connections: int = 10000,
        correlator: HTTPTransactionCorrelator | None = None,
        transaction_store: TransactionStore | None = None,
        persistence_worker: TransactionPersistenceWorker | None = None,
    ):
        if max_connections <= 0:
            raise ValueError("max_connections must be positive")

        if transaction_store is not None and persistence_worker is not None:
            raise ValueError(
                "Provide transaction_store or persistence_worker, not both"
            )

        self.publisher = publisher
        self.parser_factory = parser_factory
        self.max_connections = max_connections
        self.correlator = (
            correlator
            if correlator is not None
            else HTTPTransactionCorrelator()
        )
        self.transaction_store = transaction_store
        self.persistence_worker = persistence_worker

        # HTTP message counters.
        self.parsed_request_count = 0
        self.parsed_response_count = 0

        # Transaction processing latency metrics.
        self.transaction_processing_count = 0
        self.last_transaction_processing_latency_ms = 0.0
        self.max_transaction_processing_latency_ms = 0.0
        self.total_transaction_processing_latency_ms = 0.0

        # Capture-to-publish latency for timestamped HTTP messages.
        self.capture_to_publish_count = 0
        self.last_capture_to_publish_latency_ms = 0.0
        self.max_capture_to_publish_latency_ms = 0.0
        self.total_capture_to_publish_latency_ms = 0.0

        self.completed_transactions: deque[HTTPTransaction] = deque(
            maxlen=MAX_COMPLETED_TRANSACTIONS
        )

        # HEAD request context must cross the two directional TCP parsers.
        # The key is the exact response-direction connection ID.
        self._pending_head_responses: dict[str, int] = {}

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

    @property
    def average_transaction_processing_latency_ms(self) -> float:
        """Return average measured transaction processing latency."""
        if self.transaction_processing_count == 0:
            return 0.0

        return (
            self.total_transaction_processing_latency_ms
            / self.transaction_processing_count
        )

    @property
    def average_capture_to_publish_latency_ms(self) -> float:
        """Return average capture-to-publish latency for valid timestamps."""
        if self.capture_to_publish_count == 0:
            return 0.0
        return (
            self.total_capture_to_publish_latency_ms
            / self.capture_to_publish_count
        )

    def _record_transaction_processing_latency(
        self,
        started_at_ns: int,
    ) -> None:
        """Record processing time using the monotonic performance clock."""
        elapsed_ms = (
            time.perf_counter_ns() - started_at_ns
        ) / 1_000_000

        self.transaction_processing_count += 1
        self.last_transaction_processing_latency_ms = elapsed_ms
        self.total_transaction_processing_latency_ms += elapsed_ms
        self.max_transaction_processing_latency_ms = max(
            self.max_transaction_processing_latency_ms,
            elapsed_ms,
        )

    def _record_capture_to_publish_latency(
        self,
        captured_at: datetime | None,
        published_at: datetime,
    ) -> None:
        """Record approximate capture-to-publish latency for one message."""
        if captured_at is None or captured_at.utcoffset() is None:
            return

        elapsed_ms = (
            published_at - captured_at.astimezone(timezone.utc)
        ).total_seconds() * 1000

        if elapsed_ms < 0:
            logger.warning(
                "Skipping capture-to-publish latency: capture time is in the future"
            )
            return

        self.capture_to_publish_count += 1
        self.last_capture_to_publish_latency_ms = elapsed_ms
        self.total_capture_to_publish_latency_ms += elapsed_ms
        self.max_capture_to_publish_latency_ms = max(
            self.max_capture_to_publish_latency_ms,
            elapsed_ms,
        )

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
        reverse_id = _reverse_connection_id(connection_id)
        self._pending_head_responses.pop(connection_id, None)
        if reverse_id is not None:
            self._pending_head_responses.pop(reverse_id, None)
        self.correlator.close_connection(connection_id)

    def _sync_head_response_context(
        self,
        connection_id: str,
        parser: HTTPStreamParser,
        pending_before_feed: int,
        messages: list[HTTPMessage],
    ) -> None:
        """Move HEAD context between directional parsers and consume finals."""
        # A response parser decrements this count only when a final response
        # for a HEAD request is completed. Interim 1xx messages leave it intact.
        consumed = max(0, pending_before_feed - parser.pending_head_responses)
        if consumed:
            remaining = max(
                0, self._pending_head_responses.get(connection_id, 0) - consumed
            )
            if remaining:
                self._pending_head_responses[connection_id] = remaining
            else:
                self._pending_head_responses.pop(connection_id, None)

        reverse_id = _reverse_connection_id(connection_id)
        for message in messages:
            if message.message_type != "request" or message.method != "HEAD":
                continue
            if reverse_id is None:
                # Compatibility for single-stream callers that feed both
                # directions to one parser rather than providing a 4-tuple.
                parser.expect_head_response()
            else:
                self._pending_head_responses[reverse_id] = (
                    self._pending_head_responses.get(reverse_id, 0) + 1
                )

    def _publish_all(
        self,
        messages: list[HTTPMessage],
        connection_id: str,
    ) -> None:
        """Correlate, measure, persist, and publish complete HTTP messages."""
        for message in messages:
            message.connection_id = connection_id

            if message.message_type == "request":
                self.parsed_request_count += 1
            elif message.message_type == "response":
                self.parsed_response_count += 1

            # Measure transaction completion processing, not network latency.
            processing_started_ns = (
                time.perf_counter_ns()
                if message.message_type == "response"
                else None
            )

            transaction = self.correlator.process(message)

            if transaction is not None:
                self.completed_transactions.append(transaction)

                try:
                    if self.persistence_worker is not None:
                        # Database I/O happens in the background worker.
                        self.persistence_worker.enqueue(transaction)

                    elif self.transaction_store is not None:
                        # Compatibility path for synchronous callers.
                        self.transaction_store.save(transaction)

                except Exception:
                    logger.exception(
                        "Failed to persist HTTP transaction; "
                        "continuing message publishing"
                    )

                finally:
                    if processing_started_ns is not None:
                        self._record_transaction_processing_latency(
                            processing_started_ns
                        )

            # Preserve the existing ZeroMQ per-message event contract.
            self.publisher.publish(message)
            self._record_capture_to_publish_latency(
                message.captured_at,
                datetime.now(timezone.utc),
            )

    def feed(
        self,
        data: bytes,
        connection_id: str = DEFAULT_CONNECTION_ID,
        captured_at: datetime | None = None,
    ) -> list[HTTPMessage]:
        """Parse and publish messages with their capture timestamps."""
        parser = self._get_parser(connection_id)

        # Response bytes are parsed on the reverse-direction stream. Seed that
        # parser with outstanding HEAD context before it sees a response header.
        pending_for_direction = self._pending_head_responses.get(connection_id, 0)
        if pending_for_direction > parser.pending_head_responses:
            parser.expect_head_responses(
                pending_for_direction - parser.pending_head_responses
            )
        pending_before_feed = parser.pending_head_responses

        try:
            messages = parser.feed(data, captured_at=captured_at)
        except HTTPParseError as exc:
            for message in exc.messages:
                if message.captured_at is None:
                    message.captured_at = captured_at

            self._sync_head_response_context(
                connection_id, parser, pending_before_feed, exc.messages
            )
            self._publish_all(exc.messages, connection_id)
            self.close_connection(connection_id)
            raise

        for message in messages:
            if message.captured_at is None:
                message.captured_at = captured_at

        self._sync_head_response_context(
            connection_id, parser, pending_before_feed, messages
        )
        self._publish_all(messages, connection_id)
        return messages
