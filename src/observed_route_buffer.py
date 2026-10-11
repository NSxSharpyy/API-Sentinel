from datetime import datetime, timezone
from threading import Lock

from src.route_normalizer import normalize_route


class ObservedRouteBuffer:
    """Store unique API routes observed from HTTP transactions."""

    def __init__(self):
        self._routes = {}
        self._lock = Lock()

    def record(self, method: str, url: str) -> dict:
        """Record an observed HTTP method and normalized route."""

        if not isinstance(method, str) or not method.strip():
            raise ValueError("HTTP method must be a non-empty string.")

        method = method.strip().upper()
        route = normalize_route(url)
        key = (method, route)

        with self._lock:
            if key not in self._routes:
                self._routes[key] = {
                    "method": method,
                    "route": route,
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "observations": 0,
                }

            self._routes[key]["observations"] += 1

            return self._routes[key].copy()

    def get_routes(self) -> list[dict]:
        """Return all unique observed routes."""

        with self._lock:
            return [route.copy() for route in self._routes.values()]

    def get_count(self) -> int:
        """Return the number of unique method-route combinations."""

        with self._lock:
            return len(self._routes)

    def clear(self) -> None:
        """Clear all observed routes."""

        with self._lock:
            self._routes.clear()