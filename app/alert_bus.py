"""Thread-safe in-process publish/subscribe bus for security alerts."""
from __future__ import annotations

import queue
import threading
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class AlertEvent:
    """Standardized, safe alert fields for consumers."""

    incident_id: int
    detected_at: str
    severity: str
    title: str
    description: str | None = None
    source_ip: str | None = None
    transaction_id: int | None = None
    endpoint_id: int | None = None
    status: str = "open"

    def to_dict(self) -> dict:
        return asdict(self)


class AlertBus:
    """Deliver alerts to bounded, thread-safe subscriber queues."""

    def __init__(self, subscriber_queue_size: int = 100) -> None:
        if subscriber_queue_size <= 0:
            raise ValueError("subscriber_queue_size must be positive")

        self._subscriber_queue_size = subscriber_queue_size
        self._subscribers: set[queue.Queue[AlertEvent]] = set()
        self._lock = threading.Lock()
        self._closed = False
        self._published_count = 0
        self._delivered_count = 0
        self._dropped_delivery_count = 0

    def subscribe(self) -> queue.Queue[AlertEvent]:
        """Register a subscriber and return its queue."""
        with self._lock:
            if self._closed:
                raise RuntimeError("alert bus is closed")

            subscriber: queue.Queue[AlertEvent] = queue.Queue(
                maxsize=self._subscriber_queue_size
            )
            self._subscribers.add(subscriber)
            return subscriber

    def unsubscribe(self, subscriber: queue.Queue[AlertEvent]) -> bool:
        """Remove a subscriber; return False if it was not registered."""
        with self._lock:
            if subscriber not in self._subscribers:
                return False
            self._subscribers.remove(subscriber)
            return True

    def publish(self, event: AlertEvent) -> tuple[int, int]:
        """Publish an event and return (delivered_count, dropped_count)."""
        if not isinstance(event, AlertEvent):
            raise TypeError("event must be an AlertEvent")

        with self._lock:
            if self._closed:
                raise RuntimeError("alert bus is closed")

            self._published_count += 1
            delivered = 0
            dropped = 0

            for subscriber in tuple(self._subscribers):
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    dropped += 1
                else:
                    delivered += 1

            self._delivered_count += delivered
            self._dropped_delivery_count += dropped
            return delivered, dropped

    def snapshot(self) -> dict:
        """Return a snapshot of bus health counters."""
        with self._lock:
            return {
                "closed": self._closed,
                "subscriber_count": len(self._subscribers),
                "published_count": self._published_count,
                "delivered_count": self._delivered_count,
                "dropped_delivery_count": self._dropped_delivery_count,
            }

    def close(self) -> None:
        """Reject future publications and subscriptions."""
        with self._lock:
            self._closed = True
