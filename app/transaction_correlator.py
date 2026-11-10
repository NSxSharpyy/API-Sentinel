
from collections import deque
from dataclasses import dataclass
from time import monotonic

from app.http_reassembly import HTTPMessage


@dataclass
class HTTPTransaction:
    """A matched HTTP request and response."""

    connection_key: str
    request: HTTPMessage
    response: HTTPMessage


class HTTPTransactionCorrelator:
    """Match HTTP/1.x requests and responses in FIFO order."""

    def __init__(
        self,
        max_pending_per_connection: int = 1000,
        request_ttl_seconds: float = 60.0,
    ) -> None:
        if max_pending_per_connection <= 0:
            raise ValueError("max_pending_per_connection must be positive")
        if request_ttl_seconds <= 0:
            raise ValueError("request_ttl_seconds must be positive")

        self.max_pending_per_connection = max_pending_per_connection
        self.request_ttl_seconds = request_ttl_seconds
        self._pending: dict[str, deque[tuple[float, HTTPMessage]]] = {}
        self.unmatched_responses = 0
        self.dropped_requests = 0
        self.expired_requests = 0
        self.capacity_evicted_requests = 0
        self.connection_closed_requests = 0
        self.drop_reason_counts: dict[str, int] = {}
        self.recent_drop_samples: deque[dict[str, object]] = deque(maxlen=100)

    @staticmethod
    def _connection_key(connection_id: str | None) -> str | None:
        """Normalize a directional connection ID."""
        if not connection_id or "->" not in connection_id:
            return None

        try:
            protocol, endpoints = connection_id.split("|", 1)
            left, right = endpoints.split("->", 1)
        except ValueError:
            return None

        if not protocol or not left or not right:
            return None

        first, second = sorted((left, right))
        return f"{protocol.upper()}|{first}<->{second}"

    def _record_drop(
        self,
        created_at: float,
        message: HTTPMessage,
        reason: str,
        now: float,
    ) -> None:
        """Record bounded diagnostics without request or connection identifiers."""
        self.drop_reason_counts[reason] = (
            self.drop_reason_counts.get(reason, 0) + 1
        )

        self.recent_drop_samples.append(
            {
                "reason": reason,
                "method": (message.method or "UNKNOWN")[:16],
                "age_seconds": round(max(0.0, now - created_at), 3),
            }
        )

    def _expire(self, key: str, now: float) -> None:
        pending = self._pending.get(key)
        if pending is None:
            return

        while pending and now - pending[0][0] >= self.request_ttl_seconds:
            created_at, message = pending.popleft()
            self._record_drop(
                created_at, message, "http_request_ttl_expired", now
            )
            self.expired_requests += 1
            self.dropped_requests += 1

        if not pending:
            self._pending.pop(key, None)


    def expire_stale_requests(self, now: float | None = None) -> int:
        """Expire stale requests across all connections.

        Returns the number of requests discarded.
        """
        current_time = monotonic() if now is None else now
        dropped_before = self.dropped_requests

        for key in list(self._pending):
            self._expire(key, current_time)

        return self.dropped_requests - dropped_before

    def process(self, message: HTTPMessage) -> HTTPTransaction | None:
        """Match a response to the oldest pending request."""
        key = self._connection_key(message.connection_id)
        if key is None:
            return None

        now = monotonic()
        self._expire(key, now)

        if message.message_type == "request":
            pending = self._pending.setdefault(key, deque())

            if len(pending) >= self.max_pending_per_connection:
                created_at, evicted = pending.popleft()
                self._record_drop(
                    created_at,
                    evicted,
                    "http_pending_capacity_eviction",
                    now,
                )
                self.capacity_evicted_requests += 1
                self.dropped_requests += 1

            pending.append((now, message))
            return None

        if message.message_type == "response":
            # Most 1xx responses are interim. 101 Switching Protocols completes
            # the HTTP Upgrade exchange and must consume its pending request.
            status_code = message.status_code
            if (
                status_code is not None
                and 100 <= status_code < 200
                and status_code != 101
            ):
                return None

            pending = self._pending.get(key)

            if not pending:
                self.unmatched_responses += 1
                return None

            _, request = pending.popleft()

            if not pending:
                self._pending.pop(key, None)

            return HTTPTransaction(
                connection_key=key,
                request=request,
                response=message,
            )

        return None

    def close_connection(
        self,
        connection_id: str,
        reason: str = "explicit_connection_close",
    ) -> None:
        """Discard pending requests and record why the connection closed."""
        key = self._connection_key(connection_id)
        if key is None:
            return

        pending = self._pending.pop(key, ())
        now = monotonic()
        closed_count = len(pending)

        for created_at, message in pending:
            self._record_drop(created_at, message, reason, now)

        self.connection_closed_requests += closed_count
        self.dropped_requests += closed_count

    def pending_for_connection(self, connection_id: str) -> int:
        """Count pending requests using either connection direction."""
        key = self._connection_key(connection_id)
        if key is None:
            return 0

        return len(self._pending.get(key, ()))

    @property
    def pending_request_count(self) -> int:
        """Return the total number of pending requests."""
        return sum(len(items) for items in self._pending.values())
