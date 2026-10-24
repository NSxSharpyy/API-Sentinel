"""Bounded sliding-window suppression for repeated security alerts."""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any


class SlidingWindowAlertDeduplicator:
    """Suppress repeated alert fingerprints for a configurable time window.

    A repeated alert refreshes the window. Its incident and transaction IDs
    are deliberately excluded so repeats of the same pattern can be grouped.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        max_signatures: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, (int, float))
            or not math.isfinite(window_seconds)
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be a finite positive number")

        if (
            isinstance(max_signatures, bool)
            or not isinstance(max_signatures, int)
            or max_signatures <= 0
        ):
            raise ValueError("max_signatures must be a positive integer")

        if not callable(clock):
            raise ValueError("clock must be callable")

        self._window_seconds = float(window_seconds)
        self._max_signatures = max_signatures
        self._clock = clock
        self._last_seen: dict[tuple, float] = {}
        self._lock = threading.Lock()
        self._suppressed_count = 0
        self._unkeyed_count = 0

    @staticmethod
    def _fingerprint(event: Any) -> tuple | None:
        """Return the stable alert-pattern key, if enough context exists."""
        severity = str(getattr(event, "severity", "") or "").strip().casefold()
        title = str(getattr(event, "title", "") or "").strip().casefold()
        source_ip = str(getattr(event, "source_ip", None) or "").strip().casefold()
        endpoint_id = getattr(event, "endpoint_id", None)
        status = str(getattr(event, "status", "open") or "").strip().casefold()

        # Without a title and a source or endpoint, suppressing could group
        # unrelated alerts together. Let these events through instead.
        if not title or (not source_ip and endpoint_id is None):
            return None

        return severity, title, source_ip, endpoint_id, status

    def _purge_expired(self, now: float) -> None:
        expired = [
            key
            for key, last_seen in self._last_seen.items()
            if now - last_seen >= self._window_seconds
        ]
        for key in expired:
            del self._last_seen[key]

    def should_suppress(self, event: Any) -> bool:
        """Return True for a repeated alert inside the sliding time window."""
        key = self._fingerprint(event)
        now = float(self._clock())

        with self._lock:
            self._purge_expired(now)

            if key is None:
                self._unkeyed_count += 1
                return False

            previous = self._last_seen.get(key)
            if previous is not None and now - previous < self._window_seconds:
                self._last_seen[key] = now
                self._suppressed_count += 1
                return True

            if key not in self._last_seen and len(self._last_seen) >= self._max_signatures:
                oldest_key = min(self._last_seen, key=self._last_seen.get)
                del self._last_seen[oldest_key]

            self._last_seen[key] = now
            return False

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "window_seconds": self._window_seconds,
                "tracked_signatures": len(self._last_seen),
                "suppressed_count": self._suppressed_count,
                "unkeyed_count": self._unkeyed_count,
            }
