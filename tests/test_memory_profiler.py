import asyncio
import json

import pytest

from app.memory_profiler import DrainError, MemoryProfiler


async def queue_worker(queue, stop_event):
    while not stop_event.is_set() or not queue.empty():
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.02)
        except asyncio.TimeoutError:
            continue

        await asyncio.sleep(0.005)
        queue.task_done()


async def idle_worker(stop_event):
    await stop_event.wait()


def test_profiler_samples_and_drains_queues(tmp_path):
    async def run_test():
        raw_queue = asyncio.Queue()
        persistence_queue = asyncio.Queue()
        raw_queue.put_nowait("packet-1")
        persistence_queue.put_nowait("transaction-1")

        packet_stop = asyncio.Event()
        persistence_stop = asyncio.Event()

        packet_task = asyncio.create_task(
            queue_worker(raw_queue, packet_stop)
        )
        persistence_task = asyncio.create_task(
            queue_worker(persistence_queue, persistence_stop)
        )

        output = tmp_path / "memory.jsonl"

        profiler = MemoryProfiler(
            output_path=output,
            snapshot_provider=lambda: {
                "rss_bytes": 1000,
                "traced_current_bytes": 500,
            },
            activity_provider=lambda: (1, 1, 1),
            raw_packet_queue=raw_queue,
            persistence_queue=persistence_queue,
            packet_worker_task=packet_task,
            persistence_worker_task=persistence_task,
            sample_interval_seconds=0.05,
            drain_timeout_seconds=2,
            quiet_period_seconds=0.05,
            poll_interval_seconds=0.01,
        )

        await profiler.start()
        result = await profiler.drain()

        assert result["success"] is True
        assert raw_queue.empty()
        assert persistence_queue.empty()

        await profiler.stop()

        packet_stop.set()
        persistence_stop.set()
        await asyncio.wait_for(packet_task, timeout=1)
        await asyncio.wait_for(persistence_task, timeout=1)

        records = [
            json.loads(line)
            for line in output.read_text(encoding="utf-8").splitlines()
        ]
        events = [record["event"] for record in records]

        assert "run_start" in events
        assert "baseline" in events
        assert "drain_start" in events
        assert "drain_end" in events
        assert "queues_drained" in events
        assert "run_end" in events

    asyncio.run(run_test())


def test_drain_fails_if_packet_worker_has_stopped(tmp_path):
    async def run_test():
        raw_queue = asyncio.Queue()
        persistence_queue = asyncio.Queue()
        raw_queue.put_nowait("packet-not-processed")

        async def stopped_worker():
            return

        async def live_worker():
            await asyncio.Event().wait()

        packet_task = asyncio.create_task(stopped_worker())
        persistence_task = asyncio.create_task(live_worker())

        await packet_task

        profiler = MemoryProfiler(
            output_path=tmp_path / "failed.jsonl",
            snapshot_provider=lambda: {"rss_bytes": 1000},
            activity_provider=lambda: (1,),
            raw_packet_queue=raw_queue,
            persistence_queue=persistence_queue,
            packet_worker_task=packet_task,
            persistence_worker_task=persistence_task,
            sample_interval_seconds=1,
            drain_timeout_seconds=1,
            quiet_period_seconds=0.05,
            poll_interval_seconds=0.01,
        )

        await profiler.start()

        with pytest.raises(DrainError, match="Packet worker stopped"):
            await profiler.drain()

        await profiler.stop()
        persistence_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await persistence_task

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "setting",
    [
        {"sample_interval_seconds": 0},
        {"drain_timeout_seconds": 0},
        {"quiet_period_seconds": 0},
        {"poll_interval_seconds": 0},
    ],
)
def test_profiler_rejects_nonpositive_intervals(tmp_path, setting):
    async def worker():
        await asyncio.Event().wait()

    async def run_test():
        packet_task = asyncio.create_task(worker())
        persistence_task = asyncio.create_task(worker())

        arguments = {
            "output_path": tmp_path / "invalid.jsonl",
            "snapshot_provider": lambda: {},
            "activity_provider": lambda: (),
            "raw_packet_queue": asyncio.Queue(),
            "persistence_queue": asyncio.Queue(),
            "packet_worker_task": packet_task,
            "persistence_worker_task": persistence_task,
            "sample_interval_seconds": 1,
            "drain_timeout_seconds": 1,
            "quiet_period_seconds": 1,
            "poll_interval_seconds": 0.1,
        }
        arguments.update(setting)

        try:
            with pytest.raises(ValueError):
                MemoryProfiler(**arguments)
        finally:
            packet_task.cancel()
            persistence_task.cancel()
            await asyncio.gather(
                packet_task,
                persistence_task,
                return_exceptions=True,
            )

    asyncio.run(run_test())
