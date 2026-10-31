
import pytest

from src.route_cache import (
    clear_route_cache,
    get_route_cache_info,
    normalize_route_cached,
)


@pytest.fixture(autouse=True)
def reset_route_cache():
    clear_route_cache()
    yield
    clear_route_cache()


def test_normalize_route_cached_returns_normalized_route():
    result = normalize_route_cached("/api/users/101")

    assert result == "/api/users/{id}"


def test_repeated_route_uses_cache():
    normalize_route_cached("/api/users/101")
    normalize_route_cached("/api/users/101")

    info = get_route_cache_info()

    assert info["misses"] == 1
    assert info["hits"] == 1


def test_different_routes_are_cached_separately():
    normalize_route_cached("/api/users/101")
    normalize_route_cached("/api/orders/202")

    info = get_route_cache_info()

    assert info["misses"] == 2
    assert info["currsize"] == 2


@pytest.mark.parametrize("invalid_url", ["", "   ", None, 123])
def test_invalid_url_raises_value_error(invalid_url):
    with pytest.raises(ValueError):
        normalize_route_cached(invalid_url)


def test_cache_can_be_cleared():
    normalize_route_cached("/api/users/101")

    clear_route_cache()

    info = get_route_cache_info()

    assert info["hits"] == 0
    assert info["misses"] == 0
    assert info["currsize"] == 0


def test_cache_has_configured_capacity():
    info = get_route_cache_info()

    assert info["maxsize"] == 4096
