import asyncio
import json
import sys

import pytest
import time
from datetime import datetime, timezone

from app.ebpf_bridge import _monotonic_ns_to_utc
from app.ebpf_bridge import read_capture_events


def test_reader_converts_json_event_to_packet_dictionary():
    event = {
        "packet_id": "ebpf-1",
        "payload_hex": "474554",
        "source_ip": "10.0.0.1",
        "destination_ip": "10.0.0.2",
        "source_port": 12345,
        "destination_port": 80,
        "protocol": 6,
        "sequence_number": 100,
        "tcp_flags": 24,
    }

    async def run_test():
        events = [
            json.dumps(event),
        ]

        # Use a child Python process that writes one JSON line.
        code = (
            "import sys; "
            f"sys.stdout.write({events[0]!r} + '\\\n'); "
            "sys.stdout.flush()"
        )

        result = [
            item
            async for item in read_capture_events(
                [sys.executable, "-c", code]
            )
        ]

        assert len(result) == 1
        packet = result[0]
        assert packet["packet_id"] == "ebpf-1"
        assert packet["payload"] == b"GET"
        assert packet["source_ip"] == "10.0.0.1"
        assert packet["destination_ip"] == "10.0.0.2"
        assert packet["source_port"] == 12345
        assert packet["destination_port"] == 80
        assert packet["protocol"] == "TCP"
        assert packet["sequence_number"] == 100
        assert packet["tcp_flags"] == ["PSH", "ACK"]
        assert packet["captured_at"].tzinfo is not None

    asyncio.run(run_test())


def test_reader_ignores_invalid_json_lines():
    async def run_test():
        code = (
            "import sys; "
            "sys.stdout.write('not-json\\\n'); "
            "sys.stdout.flush()"
        )

        result = [
            item
            async for item in read_capture_events(
                [sys.executable, "-c", code]
            )
        ]

        assert result == []

    asyncio.run(run_test())


def test_reader_ignores_invalid_payload_hex():
    event = {
        "packet_id": "ebpf-2",
        "payload_hex": "not-hex!",
        "protocol": 6,
        "tcp_flags": 0,
    }

    async def run_test():
        code = (
            "import sys; "
            f"sys.stdout.write({json.dumps(event)!r} + '\\\n'); "
            "sys.stdout.flush()"
        )

        result = [
            item
            async for item in read_capture_events(
                [sys.executable, "-c", code]
            )
        ]

        assert result == []

    asyncio.run(run_test())


def test_reader_reports_successful_process_start():
    async def run_test():
        started = []

        result = [
            item
            async for item in read_capture_events(
                [sys.executable, "-c", "pass"],
                on_started=lambda: started.append(True),
            )
        ]

        assert result == []
        assert started == [True]

    asyncio.run(run_test())


def test_reader_reports_nonzero_exit_code():
    async def run_test():
        with pytest.raises(
            RuntimeError,
            match="exited unexpectedly with code 7",
        ):
            async for _ in read_capture_events(
                [sys.executable, "-c", "raise SystemExit(7)"]
            ):
                pass

    asyncio.run(run_test())

def test_monotonic_timestamp_converts_to_approximate_utc():
    captured_at_ns = time.monotonic_ns()

    converted = _monotonic_ns_to_utc(captured_at_ns)

    assert converted.tzinfo == timezone.utc
    assert isinstance(converted, datetime)

    # A timestamp captured just before conversion should be near now.
    difference = abs(
        (datetime.now(timezone.utc) - converted).total_seconds()
    )
    assert difference < 1

def test_reader_falls_back_for_invalid_monotonic_timestamp():
    event = {
        "packet_id": "ebpf-invalid-time",
        "payload_hex": "474554",
        "protocol": 6,
        "tcp_flags": 24,
        "captured_at_ns": "invalid",
    }

    async def run_test():
        code = (
            "import sys; "
            f"sys.stdout.write({json.dumps(event)!r} + '\\n'); "
            "sys.stdout.flush()"
        )

        result = [
            item
            async for item in read_capture_events(
                [sys.executable, "-c", code]
            )
        ]

        assert len(result) == 1
        assert result[0]["captured_at"].tzinfo is not None

    asyncio.run(run_test())
