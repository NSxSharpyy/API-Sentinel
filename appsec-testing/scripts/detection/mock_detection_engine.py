#!/usr/bin/env python3
"""MOCK DATA — TEMPORARY Day 16 real-time detection engine.

Tails the live billing Compose service and flags a requester accessing
invoices belonging to at least N distinct owners within a sliding window.

This is a milestone mock, not the production anomaly/correlation engine.
"""
import json
import os
import subprocess
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

APPSEC_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APPSEC_ROOT.parent

_raw_alert_path = Path(
    os.getenv(
        "DETECTION_ALERTS_PATH",
        str(APPSEC_ROOT / "logs" / "detection_alerts.jsonl"),
    )
)
ALERTS_PATH = (
    _raw_alert_path
    if _raw_alert_path.is_absolute()
    else APPSEC_ROOT / _raw_alert_path
)

WINDOW_SECONDS = float(os.getenv("DETECTION_WINDOW_SECONDS", "10"))
DISTINCT_OWNER_THRESHOLD = int(os.getenv("DETECTION_THRESHOLD", "3"))
LOG_LOOKBACK = os.getenv("DETECTION_LOG_LOOKBACK", "1s")

# requester_id -> deque of (monotonic timestamp, owner_id)
access_history = defaultdict(deque)
already_alerted = set()


def _valid_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def prune_old_entries(history, now):
    """Remove entries outside the sliding window."""
    while history and now - history[0][0] > WINDOW_SECONDS:
        history.popleft()


def emit_alert(requester_id, distinct_owners):
    """Append one contract-shaped alert and flush it immediately."""
    alert = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "alert_type": "cross_user_object_access",
        "requester_id": requester_id,
        "distinct_owners_accessed": distinct_owners,
        "window_seconds": WINDOW_SECONDS,
        "reason": (
            f"Requester {requester_id} accessed invoices belonging to "
            f"{distinct_owners} distinct owners within {WINDOW_SECONDS}s "
            f"(threshold: {DISTINCT_OWNER_THRESHOLD})."
        ),
    }

    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_PATH.open("a", encoding="utf-8") as output:
        output.write(json.dumps(alert) + "\n")
        output.flush()

    print(f"[ALERT] {alert['reason']}", flush=True)
    return alert


def process_log_line(line):
    """Process one structured billing log event; ignore unrelated/malformed lines."""
    try:
        entry = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return

    if not isinstance(entry, dict):
        return
    if entry.get("message") != "invoice accessed":
        return

    requester_id = entry.get("requester_id")
    owner_id = entry.get("owner_id")

    if not _valid_positive_int(requester_id):
        return
    if not _valid_positive_int(owner_id):
        return
    if entry.get("cross_user_access") is not True:
        return

    now = time.monotonic()
    history = access_history[requester_id]
    prune_old_entries(history, now)
    history.append((now, owner_id))

    distinct_owners = {owner for _, owner in history}
    if (
        len(distinct_owners) >= DISTINCT_OWNER_THRESHOLD
        and requester_id not in already_alerted
    ):
        emit_alert(requester_id, len(distinct_owners))
        already_alerted.add(requester_id)


def main():
    if WINDOW_SECONDS <= 0:
        raise ValueError("DETECTION_WINDOW_SECONDS must be greater than zero")
    if DISTINCT_OWNER_THRESHOLD < 1:
        raise ValueError("DETECTION_THRESHOLD must be at least 1")

    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Start each run with a clean alert file at the configured destination.
    ALERTS_PATH.write_text("", encoding="utf-8")

    command = [
        "docker", "compose", "logs",
        "--follow",
        f"--since={LOG_LOOKBACK}",
        "--no-log-prefix",
        "billing",
    ]

    print(
        "MOCK detection engine started. "
        f"Threshold={DISTINCT_OWNER_THRESHOLD} distinct owners within "
        f"{WINDOW_SECONDS}s. Alert output: {ALERTS_PATH}",
        flush=True,
    )

    proc = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        if proc.stdout is None:
            raise RuntimeError("Docker log stream did not provide stdout")

        for line in proc.stdout:
            process_log_line(line)
            if proc.poll() is not None:
                break

    except KeyboardInterrupt:
        print("Stopping mock detection engine...", flush=True)
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()

        print("MOCK detection engine stopped.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Mock detection engine error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
