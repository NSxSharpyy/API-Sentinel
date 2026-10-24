
import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _monotonic_ns_to_utc(captured_at_ns: int) -> datetime:
    """Convert kernel monotonic nanoseconds to an approximate UTC timestamp."""
    monotonic_now_ns = time.monotonic_ns()
    utc_now = datetime.now(timezone.utc)
    elapsed_ns = monotonic_now_ns - captured_at_ns

    return utc_now - timedelta(microseconds=elapsed_ns / 1000)


async def _log_reader_stderr(stream: asyncio.StreamReader) -> None:
    """Drain and log stderr without blocking the reader process."""
    while line := await stream.readline():
        message = line.decode("utf-8", errors="replace").rstrip()
        if message:
            logger.warning("Capture reader stderr: %s", message)


async def read_capture_events(
    reader_command: list[str],
    *,
    on_started: Callable[[], None] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Read newline-delimited JSON packet events from a capture process."""

    process = await asyncio.create_subprocess_exec(
        *reader_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stderr_task: asyncio.Task[None] | None = None

    try:
        if process.stdout is None:
            raise RuntimeError("Capture reader stdout is unavailable")

        if process.stderr is not None:
            stderr_task = asyncio.create_task(
                _log_reader_stderr(process.stderr)
            )

        if on_started is not None:
            on_started()

        logger.info("Capture reader started (pid=%s)", process.pid)

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            try:
                event = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Ignoring invalid capture-reader JSON line")
                continue

            if not isinstance(event, dict):
                logger.warning("Ignoring non-object capture event")
                continue

            packet_id = event.get("packet_id")
            if packet_id is None:
                logger.warning("Ignoring capture event without packet_id")
                continue

            payload_hex = event.get("payload_hex", "")
            if not isinstance(payload_hex, str):
                logger.warning("Ignoring event with invalid payload_hex")
                continue

            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError:
                logger.warning("Ignoring event with invalid payload_hex")
                continue

            protocol = {6: "TCP", 17: "UDP"}.get(event.get("protocol"))
            if protocol is None:
                logger.debug("Ignoring unsupported or undecoded packet")
                continue

            flags_value = event.get("tcp_flags", 0)
            if (
                not isinstance(flags_value, int)
                or isinstance(flags_value, bool)
                or not 0 <= flags_value <= 255
            ):
                logger.warning("Ignoring event with invalid TCP flags")
                continue

            captured_at_ns = event.get("captured_at_ns")
            if (
                isinstance(captured_at_ns, int)
                and not isinstance(captured_at_ns, bool)
                and 0 <= captured_at_ns <= time.monotonic_ns()
            ):
                captured_at = _monotonic_ns_to_utc(captured_at_ns)
            else:
                logger.warning(
                    "Capture event has missing or invalid captured_at_ns; "
                    "using reader-processing time"
                )
                captured_at = datetime.now(timezone.utc)

            flag_names = [
                name
                for mask, name in (
                    (0x01, "FIN"),
                    (0x02, "SYN"),
                    (0x04, "RST"),
                    (0x08, "PSH"),
                    (0x10, "ACK"),
                    (0x20, "URG"),
                    (0x40, "ECE"),
                    (0x80, "CWR"),
                )
                if flags_value & mask
            ]

            yield {
                "packet_id": str(packet_id),
                "captured_at": captured_at,
                "payload": payload,
                "source_ip": event.get("source_ip"),
                "destination_ip": event.get("destination_ip"),
                "source_port": event.get("source_port"),
                "destination_port": event.get("destination_port"),
                "protocol": protocol,
                "sequence_number": event.get("sequence_number"),
                "tcp_flags": flag_names,
            }

        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(
                f"Capture reader exited unexpectedly with code {return_code}"
            )

        logger.warning(
            "Capture reader exited normally; supervisor will restart it"
        )

    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

        if stderr_task is not None:
            try:
                await asyncio.wait_for(stderr_task, timeout=1)
            except asyncio.TimeoutError:
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
