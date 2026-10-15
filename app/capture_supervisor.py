import asyncio
import logging
from collections.abc import Callable

from app.ebpf_bridge import read_capture_events
from app.ring_buffer_consumer import consume_events

logger = logging.getLogger(__name__)


async def supervise_capture(
    reader_command: list[str],
    stop_event: asyncio.Event,
    *,
    restart_delay: float = 1.0,
    max_restart_delay: float = 30.0,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Supervise the capture reader with bounded exponential backoff."""

    if restart_delay <= 0:
        raise ValueError("restart_delay must be greater than zero")
    if max_restart_delay < restart_delay:
        raise ValueError("max_restart_delay must be >= restart_delay")

    delay = restart_delay

    def set_status(status: str) -> None:
        if on_status is not None:
            on_status(status)

    def reader_started() -> None:
        set_status("running")

    try:
        while not stop_event.is_set():
            set_status("starting")

            try:
                await consume_events(
                    read_capture_events(
                        reader_command,
                        on_started=reader_started,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Capture reader failed")

            if stop_event.is_set():
                break

            set_status("restarting")
            logger.warning(
                "Capture reader stopped; restarting in %.1f seconds",
                delay,
            )

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=delay,
                )
            except asyncio.TimeoutError:
                pass

            delay = min(delay * 2, max_restart_delay)

    finally:
        set_status("stopped")
        logger.info("Capture supervisor stopped")
