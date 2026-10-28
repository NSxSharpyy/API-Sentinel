#!/usr/bin/env python3
"""MOCK DATA — TEMPORARY Day 16 real-time detection engine.

Tails the live billing Compose service and flags a requester accessing
invoices belonging to at least N distinct owners within a sliding window.

This is a milestone mock, not the production anomaly/correlation engine.
"""

import json
import os
import queue
import subprocess
import sys
import threading
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
    """Return whether value is a positive integer, excluding booleans."""
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

    # Re-arm alerting once the current sliding window no longer meets the
    # incident threshold. A later qualifying incident can then alert again.
    owners_in_window = {owner for _, owner in history}
    if len(owners_in_window) < DISTINCT_OWNER_THRESHOLD:
        already_alerted.discard(requester_id)

    history.append((now, owner_id))

    distinct_owners = {owner for _, owner in history}

    if (
        len(distinct_owners) >= DISTINCT_OWNER_THRESHOLD
        and requester_id not in already_alerted
    ):
        emit_alert(requester_id, len(distinct_owners))
        already_alerted.add(requester_id)


def main():
    """Follow billing logs and promptly report startup or subprocess failures."""
    if WINDOW_SECONDS <= 0:
        raise ValueError("DETECTION_WINDOW_SECONDS must be greater than zero")

    if DISTINCT_OWNER_THRESHOLD < 1:
        raise ValueError("DETECTION_THRESHOLD must be at least 1")

    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text("", encoding="utf-8")

    command = [
        "docker",
        "compose",
        "logs",
        "--follow",
        f"--since={LOG_LOOKBACK}",
        "--no-log-prefix",
        "billing",
    ]

    try:
        proc = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise RuntimeError(
            "Could not start Docker Compose log follower; verify that Docker "
            f"is installed and available: {exc}"
        ) from exc

    if proc.stdout is None:
        proc.terminate()
        proc.wait(timeout=5)
        raise RuntimeError("Docker Compose log stream did not provide stdout")

    # A dedicated reader prevents a silent or partial log stream from
    # blocking the main thread's subprocess-health checks.
    events = queue.Queue()

    def read_stream():
        try:
            for line in proc.stdout:
                events.put(("line", line))
        except (OSError, ValueError) as exc:
            events.put(("error", exc))
        finally:
            events.put(("eof", None))

    reader = threading.Thread(target=read_stream, daemon=True)
    reader.start()

    print(
        "MOCK detection engine started. "
        f"Threshold={DISTINCT_OWNER_THRESHOLD} distinct owners within "
        f"{WINDOW_SECONDS}s. Alert output: {ALERTS_PATH}",
        flush=True,
    )

    interrupted = False
    stream_error = None

    try:
        while True:
            try:
                kind, payload = events.get(timeout=0.1)
            except queue.Empty:
                # A closed or silent stream must not prevent us noticing
                # that the Compose log follower has exited.
                if proc.poll() is not None:
                    break
                continue

            if kind == "line":
                process_log_line(payload)
            elif kind == "error":
                stream_error = payload
                break
            elif kind == "eof":
                break

    except KeyboardInterrupt:
        interrupted = True
        print("Stopping mock detection engine...", flush=True)

    finally:
        if proc.poll() is None:
            proc.terminate()

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(
                "Docker Compose log follower did not stop in time; killing it.",
                file=sys.stderr,
                flush=True,
            )
            proc.kill()
            proc.wait(timeout=5)

        if proc.stdout is not None:
            proc.stdout.close()

        print(
            "MOCK detection engine stopped. "
            f"Docker Compose exit code: {proc.returncode}",
            flush=True,
        )

    if stream_error is not None and not interrupted:
        raise RuntimeError(
            f"Error reading Docker Compose log stream: {stream_error}"
        ) from stream_error

    # This is a long-running follower. Any exit without Ctrl+C is unexpected,
    # including exit code zero, because monitoring has stopped.
    if not interrupted:
        raise RuntimeError(
            "Docker Compose log follower exited unexpectedly "
            f"with status {proc.returncode}"
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            f"Mock detection engine error: {exc}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)
