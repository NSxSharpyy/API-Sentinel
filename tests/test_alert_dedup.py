from dataclasses import replace

import pytest

from app.alert_bus import AlertBus, AlertEvent
from app.alert_dedup import SlidingWindowAlertDeduplicator


class FakeClock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_event(**changes):
    values = {
        "incident_id": 1,
        "detected_at": "2026-10-24T12:00:00+00:00",
        "severity": "high",
        "title": "Potential BOLA",
        "description": "Cross-user invoice access",
        "source_ip": "192.0.2.10",
        "transaction_id": 10,
        "endpoint_id": 5,
        "status": "open",
    }
    values.update(changes)
    return AlertEvent(**values)


def test_first_alert_passes_and_repeated_pattern_is_suppressed():
    clock = FakeClock()
    deduper = SlidingWindowAlertDeduplicator(window_seconds=10, clock=clock)
    first = make_event()

    assert deduper.should_suppress(first) is False

    # Different record IDs do not make the same alert pattern unique.
    repeated = replace(first, incident_id=2, transaction_id=11)
    clock.advance(3)
    assert deduper.should_suppress(repeated) is True

    metrics = deduper.snapshot()
    assert metrics["suppressed_count"] == 1
    assert metrics["tracked_signatures"] == 1


def test_repeated_alert_refreshes_window_and_expiry_allows_alert_again():
    clock = FakeClock()
    deduper = SlidingWindowAlertDeduplicator(window_seconds=10, clock=clock)
    event = make_event()

    assert deduper.should_suppress(event) is False
    clock.advance(8)
    assert deduper.should_suppress(event) is True

    # The duplicate refreshed the timestamp, so 9 seconds after it is
    # still inside the sliding window.
    clock.advance(9)
    assert deduper.should_suppress(event) is True

    clock.advance(10)
    assert deduper.should_suppress(event) is False


def test_distinct_source_title_endpoint_or_status_is_not_suppressed():
    deduper = SlidingWindowAlertDeduplicator()
    original = make_event()

    variants = [
        replace(original, source_ip="192.0.2.11"),
        replace(original, title="Different alert type"),
        replace(original, endpoint_id=6),
        replace(original, status="closed"),
    ]

    assert deduper.should_suppress(original) is False
    for event in variants:
        assert deduper.should_suppress(event) is False


def test_alerts_without_source_and_endpoint_are_not_grouped():
    deduper = SlidingWindowAlertDeduplicator()
    event = make_event(source_ip=None, endpoint_id=None)

    assert deduper.should_suppress(event) is False
    assert deduper.should_suppress(event) is False
    assert deduper.snapshot()["unkeyed_count"] == 2


def test_signature_cache_is_bounded():
    clock = FakeClock()
    deduper = SlidingWindowAlertDeduplicator(
        window_seconds=30,
        max_signatures=2,
        clock=clock,
    )
    first = make_event(source_ip="192.0.2.1")
    second = make_event(source_ip="192.0.2.2")
    third = make_event(source_ip="192.0.2.3")

    assert deduper.should_suppress(first) is False
    assert deduper.should_suppress(second) is False
    assert deduper.should_suppress(third) is False
    assert deduper.snapshot()["tracked_signatures"] == 2

    # The oldest signature was evicted to maintain the configured bound.
    assert deduper.should_suppress(first) is False
    assert deduper.snapshot()["tracked_signatures"] == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_seconds": 0},
        {"window_seconds": -1},
        {"window_seconds": float("inf")},
        {"max_signatures": 0},
        {"max_signatures": -1},
    ],
)
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        SlidingWindowAlertDeduplicator(**kwargs)


def test_alert_bus_suppresses_duplicate_deliveries_and_exposes_metrics():
    clock = FakeClock()
    bus = AlertBus(dedupe_window_seconds=10, dedupe_clock=clock)
    subscriber = bus.subscribe()
    first = make_event()

    assert bus.publish(first) == (1, 0)
    assert bus.publish(replace(first, incident_id=2, transaction_id=11)) == (0, 0)

    assert subscriber.get_nowait() == first
    assert subscriber.empty()

    metrics = bus.snapshot()
    assert metrics["publish_attempt_count"] == 2
    assert metrics["published_count"] == 1
    assert metrics["delivered_count"] == 1
    assert metrics["suppressed_count"] == 1
    assert metrics["dedupe_window_seconds"] == 10
