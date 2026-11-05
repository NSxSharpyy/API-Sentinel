"""Best-effort WebSocket delivery of completed HTTP transactions."""

from __future__ import annotations

import asyncio
import logging
import threading
from urllib.parse import urlsplit

from app.message_broker import (
    DISCOVERY_HTTP_TOPIC,
    HTTPTransactionSubscriber,
)

logger = logging.getLogger(__name__)


def _safe_message(message: object) -> dict | None:
    """Return dashboard-safe metadata without headers or request bodies."""
    if not isinstance(message, dict):
        return None

    uri = message.get("uri")
    endpoint = None

    if isinstance(uri, str):
        try:
            endpoint = urlsplit(uri).path or "/"
        except ValueError:
            endpoint = None

    return {
        "message_type": message.get("message_type"),
        "captured_at": message.get("captured_at"),
        "method": message.get("method"),
        "uri": endpoint,
        "status_code": message.get("status_code"),
    }


def normalize_transaction(event: object) -> dict | None:
    """Validate and minimize a completed transaction for dashboard clients."""
    if not isinstance(event, dict):
        return None

    if event.get("message_type") != "completed_transaction":
        return None

    request = _safe_message(event.get("request"))
    response = _safe_message(event.get("response"))

    if request is None or response is None:
        return None

    if request.get("message_type") != "request":
        return None

    if response.get("message_type") != "response":
        return None

    if not isinstance(request.get("method"), str):
        return None

    if not isinstance(request.get("uri"), str):
        return None

    if not isinstance(response.get("status_code"), int):
        return None

    return {
        "event_type": "http.transaction",
        "message_type": "completed_transaction",
        "connection_key": event.get("connection_key"),
        "request": request,
        "response": response,
    }


class TransactionWebSocketStream:
    """One ZeroMQ subscriber that fans out events to WebSocket clients."""

    def __init__(self, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._clients: set[asyncio.Queue] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the ZeroMQ subscriber in its own thread."""
        if self._thread is not None:
            raise RuntimeError("Transaction stream has already been started")

        self._loop = loop
        self._thread = threading.Thread(
            target=self._run,
            name="api-sentinel-transaction-subscriber",
            daemon=True,
        )
        self._thread.start()

    def subscribe(self) -> asyncio.Queue:
        """Create a bounded event queue for one WebSocket client."""
        client_queue = asyncio.Queue(maxsize=self._queue_size)
        self._clients.add(client_queue)
        return client_queue

    def unsubscribe(self, client_queue: asyncio.Queue) -> None:
        """Remove a disconnected WebSocket client."""
        self._clients.discard(client_queue)

    def _broadcast(self, event: dict) -> None:
        """Run on the asyncio event loop and deliver to connected clients."""
        for client_queue in tuple(self._clients):
            if client_queue.full():
                try:
                    client_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            try:
                client_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping transaction for a full client queue")

    def _run(self) -> None:
        """Own the ZeroMQ socket in this thread and reconnect on failures."""
        while not self._stop_event.is_set():
            subscriber = None

            try:
                subscriber = HTTPTransactionSubscriber(
                    topic=DISCOVERY_HTTP_TOPIC,
                )
                logger.info(
                    "Transaction ZeroMQ subscriber connected to topic %s",
                    DISCOVERY_HTTP_TOPIC.decode("ascii"),
                )

                while not self._stop_event.is_set():
                    event = subscriber.receive(timeout_ms=250)

                    if event is None:
                        continue

                    normalized = normalize_transaction(event)

                    if normalized is None:
                        logger.warning(
                            "Ignoring invalid completed transaction event"
                        )
                        continue

                    loop = self._loop
                    if loop is not None and not loop.is_closed():
                        loop.call_soon_threadsafe(
                            self._broadcast,
                            normalized,
                        )

            except Exception:
                if not self._stop_event.is_set():
                    logger.exception(
                        "Transaction subscriber failed; retrying shortly"
                    )
                    self._stop_event.wait(1.0)

            finally:
                if subscriber is not None:
                    try:
                        subscriber.close()
                    except Exception:
                        logger.exception(
                            "Failed to close transaction ZeroMQ subscriber"
                        )

        logger.info("Transaction ZeroMQ subscriber stopped")

    def stop(self, timeout: float = 3.0) -> None:
        """Stop the subscriber and wait for its thread to finish."""
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=timeout)

            if self._thread.is_alive():
                logger.error(
                    "Transaction subscriber thread did not stop within %.1f seconds",
                    timeout,
                )
