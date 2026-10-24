from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.http_pipeline import HTTPMessagePipeline
from app.http_reassembly import HTTPStreamParser


def test_pipeline_records_capture_to_publish_latency():
    publisher = Mock()
    pipeline = HTTPMessagePipeline(publisher=publisher)

    captured_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    parser = HTTPStreamParser()
    messages = parser.feed(
        b"GET /telemetry HTTP/1.1\r\n"
        b"Host: example.test\r\n"
        b"\r\n",
        captured_at=captured_at,
    )

    assert len(messages) == 1

    pipeline._publish_all(
        messages,
        "TCP|10.0.0.1:54321->10.0.0.2:80",
    )

    publisher.publish.assert_called_once_with(messages[0])
    assert pipeline.capture_to_publish_count == 1
    assert pipeline.last_capture_to_publish_latency_ms >= 900
    assert pipeline.max_capture_to_publish_latency_ms == (
        pipeline.last_capture_to_publish_latency_ms
    )
    assert pipeline.average_capture_to_publish_latency_ms == (
        pipeline.last_capture_to_publish_latency_ms
    )
