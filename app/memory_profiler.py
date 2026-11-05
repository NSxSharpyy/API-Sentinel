"""Bounded-memory runtime profiler and in-process queue drain controller."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryProfilerError(RuntimeError):
    """Base error raised by the memory profiler."""


class DrainError(MemoryProfilerError):
    """Raised when queues cannot be drained safely."""


class MemoryProfiler:
    """Periodically write runtime snapshots without retaining them in memory."""

    def __init__(
        self,
        *,
        output_path: str | Path,
        snapshot_provider: Callable[[], dict[str, Any]],
        activity_provider: Callable[[], object],
        raw_packet_queue: asyncio.Queue,
        persistence_queue: asyncio.Queue,
        packet_worker_task: asyncio.Task,
        persistence_worker_task: asyncio.Task,
        sample_interval_seconds: float = 60.0,
        drain_timeout_seconds: float = 120.0,
        quiet_period_seconds: float = 2.0,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        values = {
            "sample_interval_seconds": sample_interval_seconds,
            "drain_timeout_seconds": drain_timeout_seconds,
            "quiet_period_seconds": quiet_period_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        }
        for name, value in values.items():
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")

        self.output_path = Path(output_path)
        self.snapshot_provider = snapshot_provider
        self.activity_provider = activity_provider
        self.raw_packet_queue = raw_packet_queue
        self.persistence_queue = persistence_queue
        self.packet_worker_task = packet_worker_task
        self.persistence_worker_task = persistence_worker_task
        self.sample_interval_seconds = sample_interval_seconds
        self.drain_timeout_seconds = drain_timeout_seconds
        self.quiet_period_seconds = quiet_period_seconds
        self.poll_interval_seconds = poll_interval_seconds

        self._file = None
        self._sampler_task: asyncio.Task | None = None
        self._started = False
        self._stopped = False
        self._sampling_error: str | None = None

    def _write_record(self, event: str, payload: dict[str, Any]) -> None:
        if self._file is None:
            raise MemoryProfilerError("Profiler output is not open")

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "monotonic_seconds": time.monotonic(),
            "event": event,
            **payload,
        }
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def snapshot(self, event: str = "sample") -> dict[str, Any]:
        """Collect and write one in-process runtime snapshot."""
        data = self.snapshot_provider()
        if not isinstance(data, dict):
            raise MemoryProfilerError(
                "snapshot_provider must return a dictionary"
            )

        self._write_record(event, {"snapshot": data})
        return data

    async def start(self) -> None:
        """Open the JSONL output and start periodic sampling."""
        if self._started:
            raise MemoryProfilerError("Profiler has already been started")
        if self._stopped:
            raise MemoryProfilerError("Profiler cannot be restarted")

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output_path.open("a", encoding="utf-8")

        try:
            self._write_record(
                "run_start",
                {
                    "sample_interval_seconds": self.sample_interval_seconds,
                    "drain_timeout_seconds": self.drain_timeout_seconds,
                    "quiet_period_seconds": self.quiet_period_seconds,
                },
            )
            self.snapshot("baseline")
            self._started = True
            self._sampler_task = asyncio.create_task(
                self._sample_loop(),
                name="api-sentinel-memory-profiler",
            )
        except BaseException:
            self._started = False
            self._stopped = True
            if self._file is not None:
                self._file.close()
                self._file = None
            raise

    async def _sample_loop(self) -> None:
        while True:
            await asyncio.sleep(self.sample_interval_seconds)
            try:
                self.snapshot()
            except Exception as exc:
                self._sampling_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Memory profiler sampling failed")

                try:
                    self._write_record(
                        "sample_error",
                        {"error": self._sampling_error},
                    )
                except Exception:
                    logger.exception(
                        "Memory profiler could not write its sampling error; "
                        "periodic sampling is stopping"
                    )
                    return

    def _check_workers(self) -> None:
        if self.packet_worker_task.done():
            raise DrainError(
                "Packet worker stopped before drain completed"
            )
        if self.persistence_worker_task.done():
            raise DrainError(
                "Persistence worker stopped before drain completed"
            )

    async def _wait_for_queue(
        self,
        queue: asyncio.Queue,
        worker_task: asyncio.Task,
        queue_name: str,
        deadline: float,
    ) -> None:
        """Wait for queue.join while detecting worker termination."""
        join_task = asyncio.create_task(queue.join())

        try:
            while True:
                if worker_task.done():
                    raise DrainError(
                        f"{queue_name} worker stopped during drain"
                    )

                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise DrainError(
                        f"Timed out draining {queue_name}"
                    )

                done, _ = await asyncio.wait(
                    {join_task, worker_task},
                    timeout=min(remaining, self.poll_interval_seconds),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if worker_task in done:
                    raise DrainError(
                        f"{queue_name} worker stopped during drain"
                    )

                if join_task in done:
                    await join_task
                    if worker_task.done():
                        raise DrainError(
                            f"{queue_name} worker stopped after queue drain"
                        )
                    return
        finally:
            if not join_task.done():
                join_task.cancel()
                try:
                    await join_task
                except asyncio.CancelledError:
                    pass

    async def drain(self) -> dict[str, Any]:
        """Drain packet and persistence queues while workers remain alive.

        Call only after capture has stopped. Both workers must remain active
        until this method returns successfully.
        """
        if not self._started or self._stopped:
            raise MemoryProfilerError("Profiler is not running")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.drain_timeout_seconds
        stable_since: float | None = None
        previous_activity = None

        self._write_record("drain_start", {})

        try:
            while True:
                self._check_workers()

                await self._wait_for_queue(
                    self.raw_packet_queue,
                    self.packet_worker_task,
                    "Packet",
                    deadline,
                )
                await self._wait_for_queue(
                    self.persistence_queue,
                    self.persistence_worker_task,
                    "Persistence",
                    deadline,
                )

                activity = self.activity_provider()
                queues_empty = (
                    self.raw_packet_queue.empty()
                    and self.persistence_queue.empty()
                )

                if queues_empty and activity == previous_activity:
                    if stable_since is None:
                        stable_since = loop.time()

                    if loop.time() - stable_since >= self.quiet_period_seconds:
                        self._check_workers()

                        await self._wait_for_queue(
                            self.raw_packet_queue,
                            self.packet_worker_task,
                            "Packet",
                            deadline,
                        )
                        await self._wait_for_queue(
                            self.persistence_queue,
                            self.persistence_worker_task,
                            "Persistence",
                            deadline,
                        )

                        final_activity = self.activity_provider()
                        if (
                            self.raw_packet_queue.empty()
                            and self.persistence_queue.empty()
                            and final_activity == activity
                        ):
                            result = {
                                "success": True,
                                "raw_packet_queue_depth":
                                    self.raw_packet_queue.qsize(),
                                "persistence_queue_depth":
                                    self.persistence_queue.qsize(),
                                "activity_signature": final_activity,
                                "quiet_period_seconds":
                                    self.quiet_period_seconds,
                            }
                            self.snapshot("queues_drained")
                            self._write_record("drain_end", result)
                            return result

                        previous_activity = final_activity
                        stable_since = None
                else:
                    previous_activity = activity
                    stable_since = loop.time() if queues_empty else None

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise DrainError("Timed out waiting for stable drain")

                await asyncio.sleep(
                    min(self.poll_interval_seconds, remaining)
                )

        except Exception as exc:
            result = {
                "success": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "raw_packet_queue_depth": self.raw_packet_queue.qsize(),
                "persistence_queue_depth": self.persistence_queue.qsize(),
            }
            self._write_record("drain_end", result)
            raise

    async def stop(self) -> None:
        """Stop sampling and close the JSONL output."""
        if self._stopped:
            return

        if self._sampler_task is not None:
            self._sampler_task.cancel()
            try:
                await self._sampler_task
            except asyncio.CancelledError:
                pass
            self._sampler_task = None

        write_error = None
        if self._file is not None:
            try:
                self._write_record(
                    "run_end",
                    {"sampling_error": self._sampling_error},
                )
            except Exception as exc:
                write_error = exc
                logger.exception("Could not write profiler run_end record")
            finally:
                self._file.close()
                self._file = None

        self._stopped = True

        if write_error is not None:
            raise write_error
