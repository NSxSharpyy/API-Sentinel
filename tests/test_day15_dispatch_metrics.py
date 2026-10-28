import asyncio
import time
from datetime import datetime, timezone

from app import queues
from app.ring_buffer_consumer import consume_events


def test_dispatch_metrics_calculate_bounded_percentiles():
    metrics = queues.RingBufferDispatchMetrics(sample_capacity=3)
    for elapsed_ns in (100_000, 1_200_000, 2_000_000, 500_000):
        metrics.record(elapsed_ns)

    result = metrics.snapshot()
    assert result["count"] == 4
    assert result["sample_count"] == 3
    assert result["p50_latency_us"] == 1_200.0
    assert result["p95_latency_us"] == 2_000.0
    assert result["p99_latency_us"] == 2_000.0
    assert result["under_1ms_sample_count"] == 1
    assert abs(result["under_1ms_sample_percent"] - 100 / 3) < 0.001


def test_consumer_records_reader_callback_to_queue_dispatch(monkeypatch):
    async def scenario():
        raw_queue = asyncio.Queue(maxsize=2)
        metrics = queues.RingBufferDispatchMetrics(sample_capacity=16)
        monkeypatch.setattr(queues, "raw_packet_queue", raw_queue)
        monkeypatch.setattr(queues, "ring_buffer_dispatch_metrics", metrics)

        for counter in (
            "accepted_packet_count",
            "accepted_tcp_event_count",
            "accepted_udp_event_count",
            "rejected_packet_count",
            "dropped_packet_count",
            "raw_packet_queue_max_depth",
        ):
            monkeypatch.setattr(queues, counter, 0)

        reader_started_ns = time.perf_counter_ns() - 500_000

        async def events():
            yield {
                "packet_id": "day15-metric-test",
                "captured_at": datetime.now(timezone.utc),
                "payload": b"test-payload",
                "protocol": "TCP",
                "_ring_buffer_read_at_ns": reader_started_ns,
            }

        stats = await consume_events(events())
        assert stats.accepted == 1
        assert stats.rejected == 0
        assert stats.dropped == 0

        packet = raw_queue.get_nowait()
        assert packet.packet_id == "day15-metric-test"

        result = metrics.snapshot()
        assert result["count"] == 1
        assert result["sample_count"] == 1
        assert result["last_latency_us"] >= 500.0
        assert result["p50_latency_us"] == result["last_latency_us"]

    asyncio.run(scenario())
