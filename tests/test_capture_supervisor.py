import asyncio

import pytest

from app.capture_supervisor import supervise_capture


def test_supervisor_restarts_after_reader_returns(monkeypatch):
    async def run_test():
        stop_event = asyncio.Event()
        statuses = []
        attempts = 0

        async def fake_consume(events):
            nonlocal attempts
            attempts += 1

            if attempts == 2:
                stop_event.set()

        monkeypatch.setattr(
            "app.capture_supervisor.consume_events",
            fake_consume,
        )

        await supervise_capture(
            ["fake-reader"],
            stop_event,
            restart_delay=0.001,
            max_restart_delay=0.002,
            on_status=statuses.append,
        )

        assert attempts == 2
        assert "restarting" in statuses
        assert statuses[-1] == "stopped"

    asyncio.run(run_test())


def test_supervisor_propagates_cancellation(monkeypatch):
    async def run_test():
        entered = asyncio.Event()

        async def fake_consume(events):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(
            "app.capture_supervisor.consume_events",
            fake_consume,
        )

        task = asyncio.create_task(
            supervise_capture(
                ["fake-reader"],
                asyncio.Event(),
            )
        )

        await entered.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_test())


def test_supervisor_rejects_invalid_delays():
    async def run_test():
        with pytest.raises(ValueError):
            await supervise_capture(
                ["fake-reader"],
                asyncio.Event(),
                restart_delay=0,
            )

        with pytest.raises(ValueError):
            await supervise_capture(
                ["fake-reader"],
                asyncio.Event(),
                restart_delay=2,
                max_restart_delay=1,
            )

    asyncio.run(run_test())


def test_supervisor_uses_bounded_exponential_backoff(monkeypatch):
    async def run_test():
        stop_event = asyncio.Event()
        attempts = 0
        delays = []

        async def fake_consume(events):
            nonlocal attempts
            attempts += 1

            if attempts == 4:
                stop_event.set()

        original_wait_for = asyncio.wait_for

        async def recording_wait_for(awaitable, timeout):
            delays.append(timeout)
            return await original_wait_for(awaitable, timeout=timeout)

        monkeypatch.setattr(
            "app.capture_supervisor.consume_events",
            fake_consume,
        )
        monkeypatch.setattr(
            "app.capture_supervisor.asyncio.wait_for",
            recording_wait_for,
        )

        await supervise_capture(
            ["fake-reader"],
            stop_event,
            restart_delay=0.01,
            max_restart_delay=0.02,
        )

        assert attempts == 4
        assert delays == [0.01, 0.02, 0.02]

    asyncio.run(run_test())
