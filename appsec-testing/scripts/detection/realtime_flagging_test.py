#!/usr/bin/env python3
"""Day 16 real-time flagging milestone grader.

MOCK DATA — TEMPORARY: validates the real-time measurement pipeline against
the temporary mock detection engine, not the production detection engine.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

APPSEC_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APPSEC_ROOT.parent
ENGINE = APPSEC_ROOT / "scripts" / "detection" / "mock_detection_engine.py"
ATTACK = APPSEC_ROOT / "scripts" / "attacks" / "bola_attack.py"


def read_jsonl(path):
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def wait_for_engine_start(proc, log_path, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            if "MOCK detection engine started." in text:
                return True
        if proc.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--end-id", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.start_id < 1 or args.end_id < args.start_id:
        parser.error("invoice ID range must satisfy 1 <= start-id <= end-id")
    if args.delay < 0:
        parser.error("--delay cannot be negative")

    logs_root = APPSEC_ROOT / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="realtime_flagging_", dir=logs_root))
    attack_dir = run_dir / "attack"
    attack_dir.mkdir()
    alert_path = run_dir / "detection_alerts.jsonl"
    engine_log = run_dir / "engine.log"
    attack_log = run_dir / "attack_harness.log"
    report_path = run_dir / "realtime_flagging_report.json"

    env = os.environ.copy()
    env["DETECTION_ALERTS_PATH"] = str(alert_path)
    env["DETECTION_WINDOW_SECONDS"] = "10"
    env["DETECTION_THRESHOLD"] = "3"

    engine_proc = None
    attack_proc = None
    engine_handle = None
    attack_handle = None
    attack_start = None
    attack_start_monotonic = None
    result = {
        "mode": "MOCK DATA — TEMPORARY",
        "run_dir": str(run_dir),
        "timeout_seconds": args.timeout_seconds,
        "threshold_distinct_owners": 3,
        "window_seconds": 10,
        "status": "FAIL",
        "failures": [],
    }

    try:
        # Engine starts first; wait for its explicit readiness message.
        engine_handle = engine_log.open("w", encoding="utf-8")
        engine_proc = subprocess.Popen(
            [sys.executable, str(ENGINE)],
            cwd=APPSEC_ROOT,
            env=env,
            stdout=engine_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if not wait_for_engine_start(engine_proc, engine_log):
            result["failures"].append(
                "Mock engine did not report readiness within 8 seconds"
            )
            return write_report(result, report_path)

        command = [
            sys.executable, str(ATTACK),
            "--mode", "sweep",
            "--start-id", str(args.start_id),
            "--end-id", str(args.end_id),
            "--delay", str(args.delay),
            "--output-dir", str(attack_dir),
        ]

        attack_start = datetime.now(timezone.utc)
        attack_start_monotonic = time.monotonic()
        attack_handle = attack_log.open("w", encoding="utf-8")
        attack_proc = subprocess.Popen(
            command,
            cwd=APPSEC_ROOT,
            env=env,
            stdout=attack_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

        deadline = attack_start_monotonic + args.timeout_seconds
        first_alert = None

        while time.monotonic() < deadline:
            alerts = read_jsonl(alert_path)
            if alerts:
                first_alert = alerts[0]
                break
            if attack_proc.poll() is not None:
                # The attack may finish before the log stream emits its alert.
                time.sleep(0.1)
            else:
                time.sleep(0.05)

        # Give the harness a short chance to finish after an early alert.
        if attack_proc.poll() is None:
            try:
                attack_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                attack_proc.terminate()
                try:
                    attack_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    attack_proc.kill()
                    attack_proc.wait()

        attack_records = read_jsonl(attack_dir / "bola_attack.jsonl")
        successful_cross_user = [
            row for row in attack_records
            if row.get("cross_user_access") is True
            and isinstance(row.get("owner_id"), int)
            and not isinstance(row.get("owner_id"), bool)
            and isinstance(row.get("attacker_id"), int)
            and not isinstance(row.get("attacker_id"), bool)
        ]
        distinct_owners = sorted({
            row["owner_id"] for row in successful_cross_user
        })
        attacker_ids = sorted({
            row["attacker_id"] for row in successful_cross_user
        })

        result.update({
            "attack_exit_code": attack_proc.returncode,
            "attack_record_count": len(attack_records),
            "cross_user_record_count": len(successful_cross_user),
            "distinct_cross_user_owners": distinct_owners,
            "attacker_ids": attacker_ids,
            "attack_output": str(attack_dir / "bola_attack.jsonl"),
            "alert_output": str(alert_path),
            "engine_log": str(engine_log),
            "attack_log": str(attack_log),
        })

        if attack_proc.returncode != 0:
            result["failures"].append(
                f"Attack harness exited with code {attack_proc.returncode}"
            )
        if len(distinct_owners) < 3:
            result["failures"].append(
                "Attack sweep did not confirm cross-user access to at least "
                "3 distinct owners; increase --end-id or inspect seeded data"
            )

        # Read again after the harness has exited, in case the alert arrived
        # while the attack process was completing.
        alerts = read_jsonl(alert_path)
        if first_alert is None and alerts:
            first_alert = alerts[0]

        if first_alert is None:
            result["failures"].append(
                f"No alert observed within {args.timeout_seconds:.1f} seconds"
            )
        else:
            result["alert"] = first_alert
            try:
                alert_time = datetime.fromisoformat(
                    first_alert["ts"].replace("Z", "+00:00")
                )
                if alert_time.tzinfo is None:
                    raise ValueError("alert timestamp is missing timezone")
                latency = (alert_time - attack_start).total_seconds()
                result["detection_latency_seconds"] = round(latency, 4)
                if latency < 0:
                    result["failures"].append(
                        "Alert timestamp precedes the attack start timestamp"
                    )
                elif latency > args.timeout_seconds:
                    result["failures"].append(
                        f"Detection latency {latency:.3f}s exceeds "
                        f"{args.timeout_seconds:.3f}s target"
                    )
            except (KeyError, TypeError, ValueError) as exc:
                result["failures"].append(
                    f"Invalid alert timestamp or schema: {exc}"
                )

            if first_alert.get("alert_type") != "cross_user_object_access":
                result["failures"].append("Unexpected alert_type")
            if first_alert.get("distinct_owners_accessed", 0) < 3:
                result["failures"].append(
                    "Alert reports fewer than 3 distinct owners"
                )
            if attacker_ids and first_alert.get("requester_id") not in attacker_ids:
                result["failures"].append(
                    "Alert requester_id does not match the attacker's ID"
                )

        if not result["failures"]:
            result["status"] = "PASS"

        return write_report(result, report_path)

    finally:
        # Always clean up child processes, including on exceptions.
        for proc in (attack_proc, engine_proc):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        for handle in (attack_handle, engine_handle):
            if handle is not None:
                handle.close()


def write_report(result, report_path):
    report_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"\nReport written to: {report_path}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
