from concurrent.futures import ThreadPoolExecutor

import pytest

from app.alert_bus import AlertBus, AlertEvent


def make_alert(
    incident_id: int = 1,
    *,
    source_ip: str = "192.0.2.10",
) -> AlertEvent:
    return AlertEvent(
        incident_id=incident_id,
        detected_at="2026-10-24T12:00:00+00:00",
        severity="high",
        title="Test security incident",
        description="Synthetic test event",
        source_ip=source_ip,
        transaction_id=42,
        endpoint_id=7,
        status="open",
    )


def test_publish_delivers_to_every_subscriber():
    bus = AlertBus()
    first = bus.subscribe()
    second = bus.subscribe()
    event = make_alert()

    assert bus.publish(event) == (2, 0)
    assert first.get_nowait() == event
    assert second.get_nowait() == event
    assert event.to_dict()["incident_id"] == 1

    metrics = bus.snapshot()
    assert metrics["published_count"] == 1
    assert metrics["delivered_count"] == 2
    assert metrics["dropped_delivery_count"] == 0


def test_full_subscriber_drops_only_its_delivery():
    bus = AlertBus(subscriber_queue_size=1)
    slow_subscriber = bus.subscribe()
    active_subscriber = bus.subscribe()

    first_event = make_alert(1)
    second_event = make_alert(2, source_ip="192.0.2.11")

    assert bus.publish(first_event) == (2, 0)
    assert active_subscriber.get_nowait() == first_event

    assert bus.publish(second_event) == (1, 1)
    assert slow_subscriber.get_nowait() == first_event
    assert active_subscriber.get_nowait() == second_event

    metrics = bus.snapshot()
    assert metrics["published_count"] == 2
    assert metrics["delivered_count"] == 3
    assert metrics["dropped_delivery_count"] == 1


def test_unsubscribe_stops_future_delivery():
    bus = AlertBus()
    subscriber = bus.subscribe()

    assert bus.unsubscribe(subscriber) is True
    assert bus.unsubscribe(subscriber) is False
    assert bus.publish(make_alert()) == (0, 0)
    assert subscriber.empty()


def test_invalid_queue_size_is_rejected():
    with pytest.raises(ValueError, match="must be positive"):
        AlertBus(subscriber_queue_size=0)


def test_closed_bus_rejects_new_subscriptions_and_publications():
    bus = AlertBus()
    bus.close()

    with pytest.raises(RuntimeError, match="closed"):
        bus.subscribe()

    with pytest.raises(RuntimeError, match="closed"):
        bus.publish(make_alert())


def test_publish_is_thread_safe():
    bus = AlertBus(subscriber_queue_size=128)
    subscriber = bus.subscribe()

    def publish_one(number: int):
        return bus.publish(make_alert(number, source_ip=f"192.0.2.{number}"))

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(publish_one, range(1, 101)))

    assert results == [(1, 0)] * 100
    assert subscriber.qsize() == 100

    metrics = bus.snapshot()
    assert metrics["published_count"] == 100
    assert metrics["delivered_count"] == 100
    assert metrics["dropped_delivery_count"] == 0


def test_repeated_alert_is_suppressed_in_bus():
    from dataclasses import replace

    clock = iter([100.0, 101.0]).__next__
    bus = AlertBus(dedupe_clock=clock)
    subscriber = bus.subscribe()
    first = make_alert()
    duplicate = replace(first, incident_id=2, transaction_id=43)

    assert bus.publish(first) == (1, 0)
    assert bus.publish(duplicate) == (0, 0)
    assert subscriber.get_nowait() == first
    assert subscriber.empty()
    assert bus.snapshot()["suppressed_count"] == 1
