
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


async def read_capture_events(
    reader_command: list[str],
) -> AsyncIterator[dict[str, Any]]:
    """Read newline-delimited JSON packet events from a capture process."""

    process = await asyncio.create_subprocess_exec(
        *reader_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    if process.stdout is None:
        process.kill()
        await process.wait()
        raise RuntimeError("Capture reader stdout is unavailable")

    try:
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
                logger.warning("Ignoring capture event that is not a JSON object")
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

            protocol_number = event.get("protocol")
            protocol = {
                6: "TCP",
                17: "UDP",
            }.get(protocol_number)

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
                "captured_at": datetime.now(timezone.utc),
                "payload": payload,
                "source_ip": event.get("source_ip"),
                "destination_ip": event.get("destination_ip"),
                "source_port": event.get("source_port"),
                "destination_port": event.get("destination_port"),
                "protocol": protocol,
                "sequence_number": event.get("sequence_number"),
                "tcp_flags": flag_names,
            }

    finally:
        if process.returncode is None:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
