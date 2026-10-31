
"""
Bounded, thread-safe cache for normalized API routes.
"""

from functools import lru_cache

from src.route_normalizer import normalize_route


DEFAULT_CACHE_SIZE = 4096


@lru_cache(maxsize=DEFAULT_CACHE_SIZE)
def _cached_normalize_route(url: str) -> str:
    """Normalize a route and cache the result."""
    return normalize_route(url)


def normalize_route_cached(url: str) -> str:
    """Return a cached normalized route."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")

    return _cached_normalize_route(url)


def get_route_cache_info():
    """Return cache hit, miss and capacity statistics."""
    info = _cached_normalize_route.cache_info()

    return {
        "hits": info.hits,
        "misses": info.misses,
        "maxsize": info.maxsize,
        "currsize": info.currsize,
    }


def clear_route_cache():
    """Clear cached routes and reset cache statistics."""
    _cached_normalize_route.cache_clear()
