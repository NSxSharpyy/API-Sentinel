"""Forward sent-request JSONL records to the mock ingestion receiver."""

import argparse
import json
import time
from pathlib import Path

import requests

DEFAULT_SOURCE = "logs/sent_requests.jsonl"
DEFAULT_RECEIVER = "http://127.0.0.1:5099/capture"


def forward_file(source, receiver, delay=0.0):
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Sent-request log not found: {source}")

    stats = {
        "read": 0,
        "forwarded": 0,
        "dropped": 0,
        "failed": 0,
        "invalid": 0,
    }

    with requests.Session() as session, source.open(
        encoding="utf-8"
    ) as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                stats["invalid"] += 1
                print(f"[INVALID] line {line_number}: {exc}")
                continue

            if not isinstance(record, dict):
                stats["invalid"] += 1
                print(f"[INVALID] line {line_number}: expected JSON object")
                continue

            request_id = record.get("request_id")
            if not isinstance(request_id, str) or not request_id.strip():
                stats["invalid"] += 1
                print(f"[INVALID] line {line_number}: missing request_id")
                continue

            payload = {
                "request_id": request_id,
                "service": record.get("service", "unknown"),
                "method": record.get("method", "UNKNOWN"),
                "path": record.get("path", ""),
                "source": record.get("source", "unknown"),
            }

            stats["read"] += 1
            try:
                response = session.post(
                    receiver,
                    json=payload,
                    timeout=5,
                )
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

            if delay > 0:
                time.sleep(delay)

    print("\n===== Forwarder summary =====")
    for key, value in stats.items():
        print(f"{key.capitalize()}: {value}")

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--receiver", default=DEFAULT_RECEIVER)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    if args.delay < 0:
        parser.error("--delay cannot be negative")

    forward_file(args.source, args.receiver, args.delay)


if __name__ == "__main__":
    main()
