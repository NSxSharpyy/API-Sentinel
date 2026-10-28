"""Forward sent-request JSONL records to the mock ingestion receiver."""

import argparse
import json
import time
from pathlib import Path

import requests

DEFAULT_SOURCE = "logs/sent_requests.jsonl"
DEFAULT_RECEIVER = "http://127.0.0.1:5099/capture"


def forward_file(
    source,
    receiver,
    delay=0.0,
    follow=False,
    duration=40.0,
    poll_interval=0.1,
    stop_file=None,
):
    source = Path(source)

    if not source.is_file():
        raise FileNotFoundError(f"Sent-request log not found: {source}")
    if delay < 0:
        raise ValueError("delay cannot be negative")
    if duration <= 0:
        raise ValueError("duration must be greater than zero")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be greater than zero")

    stats = {
        "read": 0,
        "forwarded": 0,
        "dropped": 0,
        "failed": 0,
        "invalid": 0,
    }

    def forward_line(session, line, line_number):
        if not line.strip():
            return

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            stats["invalid"] += 1
            print(f"[INVALID] line {line_number}: {exc}")
            return

        if not isinstance(record, dict):
            stats["invalid"] += 1
            print(f"[INVALID] line {line_number}: expected JSON object")
            return

        request_id = record.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            stats["invalid"] += 1
            print(f"[INVALID] line {line_number}: missing request_id")
            return

        payload = {
            "request_id": request_id,
            "service": record.get("service", "unknown"),
            "method": record.get("method", "UNKNOWN"),
            "path": record.get("path", ""),
            "source": record.get("source", "unknown"),
        }

        stats["read"] += 1

        try:
            response = session.post(receiver, json=payload, timeout=5)

            if response.status_code == 201:
                stats["forwarded"] += 1
                print(f"[CAPTURED] {request_id}")
            elif response.status_code == 202:
                stats["dropped"] += 1
                print(f"[DROPPED] {request_id}")
            else:
                stats["failed"] += 1
                print(
                    f"[FAILED] {request_id}: "
                    f"HTTP {response.status_code} {response.text[:200]}"
                )
        except requests.RequestException as exc:
            stats["failed"] += 1
            print(f"[FAILED] {request_id}: {exc}")

        if delay:
            time.sleep(delay)

    with requests.Session() as session, source.open(
        encoding="utf-8"
    ) as file:
        if follow:
            deadline = time.monotonic() + duration
            line_number = 0
            print(f"Following {source} for {duration:g} seconds...")

            while time.monotonic() < deadline:
                line = file.readline()

                if line:
                    line_number += 1
                    forward_line(session, line, line_number)
                elif stop_file is not None and Path(stop_file).exists():
                    print(f"Stop signal received: {stop_file}")
                    break
                else:
                    time.sleep(
                        min(
                            poll_interval,
                            max(0, deadline - time.monotonic()),
                        )
                    )
        else:
            for line_number, line in enumerate(file, 1):
                forward_line(session, line, line_number)

    print("\n===== Forwarder summary =====")
    for key, value in stats.items():
        print(f"{key.capitalize()}: {value}")

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--receiver", default=DEFAULT_RECEIVER)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Continue reading newly appended JSONL records",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=40.0,
        help="Follow duration in seconds (default: 40)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Seconds between checks for new records (default: 0.1)",
    )
    parser.add_argument(
        "--stop-file",
        help="In follow mode, stop after this file exists and the source is drained",
    )
    args = parser.parse_args()

    if args.delay < 0:
        parser.error("--delay cannot be negative")
    if args.duration <= 0:
        parser.error("--duration must be greater than zero")
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than zero")

    forward_file(
        args.source,
        args.receiver,
        delay=args.delay,
        follow=args.follow,
        duration=args.duration,
        poll_interval=args.poll_interval,
        stop_file=args.stop_file,
    )


if __name__ == "__main__":
    main()
