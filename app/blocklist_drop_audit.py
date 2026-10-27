"""Persistence and supervision for actual Day 17 kernel drop events."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BlockedTransactionAudit

logger = logging.getLogger(__name__)

DROP_EVENTS_PIN = "/sys/fs/bpf/api_sentinel_day17_drop_events"


class BlockedTransactionAuditStore:
    """Validate and persist one kernel drop event per audit row."""

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _port(value: object, field: str) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 65535
        ):
            raise ValueError(f"{field} must be an integer from 0 to 65535")
        return value

    def record_drop(self, event: Mapping[str, object]) -> int:
        if not isinstance(event, Mapping):
            raise ValueError("Drop event must be an object")

        try:
            source_ip = ipaddress.ip_address(event.get("source_ip"))
            target_ip = ipaddress.ip_address(event.get("destination_ip"))
        except ValueError as exc:
            raise ValueError("Drop event contains an invalid IP address") from exc

        if (
            not isinstance(source_ip, ipaddress.IPv4Address)
            or not isinstance(target_ip, ipaddress.IPv4Address)
        ):
            raise ValueError("Day 17 enforcement currently supports IPv4 only")

        source_port = self._port(event.get("source_port"), "source_port")
        target_port = self._port(event.get("destination_port"), "destination_port")

        protocol = event.get("protocol")
        if protocol not in ("TCP", "UDP", "OTHER"):
            raise ValueError("protocol must be TCP, UDP, or OTHER")

        rule_id = event.get("rule_id")
        if (
            not isinstance(rule_id, str)
            or not rule_id.strip()
            or len(rule_id) > 128
        ):
            raise ValueError("rule_id is required and must be at most 128 characters")

        interface_index = event.get("interface_index")
        if (
            isinstance(interface_index, bool)
            or not isinstance(interface_index, int)
            or not 1 <= interface_index <= 0xFFFFFFFF
        ):
            raise ValueError("interface_index must be a positive uint32")

        captured_ns = event.get("captured_at_ns")
        monotonic_now_ns = time.monotonic_ns()
        if (
            isinstance(captured_ns, bool)
            or not isinstance(captured_ns, int)
            or captured_ns <= 0
            or captured_ns > monotonic_now_ns
        ):
            raise ValueError("captured_at_ns is invalid")

        # The eBPF timestamp and Python monotonic clock share the host clock.
        elapsed_us = (monotonic_now_ns - captured_ns) / 1000
        dropped_at = datetime.now(timezone.utc) - timedelta(
            microseconds=elapsed_us
        )
        endpoint = (
            f"{target_ip}:{target_port}" if target_port else str(target_ip)
        )

        record = BlockedTransactionAudit(
            dropped_at=dropped_at,
            attacker_identifier=str(source_ip),
            attacker_ip=str(source_ip),
            target_endpoint=endpoint,
            target_ip=str(target_ip),
            source_port=source_port,
            target_port=target_port,
            protocol=protocol,
            rule_id=rule_id,
            interface_index=interface_index,
        )

        with self.session_factory() as session:
            try:
                session.add(record)
                session.commit()
                return int(record.id)
            except Exception:
                session.rollback()
                raise


async def _drain_stderr(stream: asyncio.StreamReader) -> None:
    while line := await stream.readline():
        message = line.decode("utf-8", errors="replace").rstrip()
        if message:
            logger.info("Day 19 drop reader: %s", message)


async def _read_line_or_stop(
    stream: asyncio.StreamReader,
    stop_event: asyncio.Event,
) -> bytes | None:
    line_task = asyncio.create_task(stream.readline())
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        (line_task, stop_task),
        return_when=asyncio.FIRST_COMPLETED,
    )

    stopped = stop_task in done and stop_task.result()
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    if stopped:
        return None
    if not stop_task.done():
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)

    return line_task.result()


async def supervise_blocklist_drop_audit(
    reader_command: list[str],
    stop_event: asyncio.Event,
    audit_store: BlockedTransactionAuditStore,
    *,
    restart_delay: float = 1.0,
) -> None:
    """Restart the JSON reader after failure and persist valid events."""
    if restart_delay <= 0:
        raise ValueError("restart_delay must be positive")

    while not stop_event.is_set():
        process = None
        stderr_task = None
        try:
            process = await asyncio.create_subprocess_exec(
                *reader_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stderr_task = asyncio.create_task(_drain_stderr(process.stderr))
            logger.info("Day 19 drop-audit reader started (pid=%s)", process.pid)

            while not stop_event.is_set():
                line = await _read_line_or_stop(process.stdout, stop_event)
                if line is None or not line:
                    break
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError("event must be a JSON object")
                    await asyncio.to_thread(audit_store.record_drop, event)
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Ignoring invalid Day 19 audit event")
                except Exception:
                    logger.exception("Failed to persist Day 19 drop audit event")

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Day 19 drop-audit reader failed")

        finally:
            if process is not None and process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

            if stderr_task is not None:
                try:
                    await asyncio.wait_for(stderr_task, timeout=1)
                except asyncio.TimeoutError:
                    stderr_task.cancel()
                    await asyncio.gather(stderr_task, return_exceptions=True)

        if not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=restart_delay)
            except asyncio.TimeoutError:
                pass
