"""Day 21 concurrent legitimate-traffic and attack verification.

This runner validates application-layer simulation only. It does not claim
that the Day 21 adapter proves eBPF or kernel packet drops.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = REPO_ROOT / "appsec-testing"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_PATH = LOG_DIR / "zero_drop_report.json"
ENFORCER_URL = "http://127.0.0.1:8004"
WRAPPER_URL = "http://127.0.0.1:8005"
DURATION_SECONDS = 25


def evaluate_report(report):
    """Return acceptance checks and an overall PASS/FAIL result."""
    checks = {
        "legitimate_traffic_observed": report.get("legitimate_request_count", 0) > 0,
        "legitimate_success_rate_is_100_percent": (
            report.get("legitimate_success_rate") == 1.0
        ),
        "zero_legitimate_failures": report.get("legitimate_failure_count") == 0,
        "attacker_blocked": report.get("attacker_blocked_count", 0) > 0,
        "enforcement_was_active": report.get("enforcement_was_active") is True,
    }
    report["checks"] = checks
    report["overall"] = "PASS" if all(checks.values()) else "FAIL"
    return report


def wait_for_health(url, process, timeout=12):
    deadline = time.monotonic() + timeout
    last_error = "health endpoint not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Process exited early with code {process.returncode}: {url}"
            )
        try:
            response = requests.get(url, timeout=0.5)
            if response.ok:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"Health check failed for {url}: {last_error}")


def read_jsonl(path):
    records = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def newest_traffic_log(directory):
    candidates = sorted(directory.glob("traffic_*.jsonl"))
    return candidates[-1] if candidates else None


def run():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    traffic_dir = LOG_DIR / "day21-traffic"
    attack_dir = LOG_DIR / "day21-attack"
    traffic_dir.mkdir(parents=True, exist_ok=True)
    attack_dir.mkdir(parents=True, exist_ok=True)

    # Use a fresh traffic directory so this run cannot count stale records.
    for old_file in traffic_dir.glob("*"):
        if old_file.is_file():
            old_file.unlink()
    for old_file in attack_dir.glob("*"):
        if old_file.is_file():
            old_file.unlink()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["DAY21_ENFORCER_PORT"] = "8004"
    env["DAY21_ENFORCER_HOST"] = "127.0.0.1"
    env["DAY21_ATTACK_THRESHOLD"] = "3"
    env["DAY21_ATTACK_WINDOW_SECONDS"] = "10"
    env["DAY21_ATTACK_BLOCK_SECONDS"] = "20"
    env["DAY21_BILLING_UPSTREAM_URL"] = "http://127.0.0.1:5004"
    env["ENFORCER_URL"] = ENFORCER_URL
    env["DIRECT_UPSTREAM_URL"] = "http://127.0.0.1:5004"
    env["WRAPPER_HOST"] = "127.0.0.1"
    env["WRAPPER_PORT"] = "8005"

    processes = []
    opened_logs = []
    report = {
        "day": 21,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "evidence_type": "application_layer_simulation",
        "kernel_drop_proof": False,
        "duration_seconds": DURATION_SECONDS,
        "threshold": 3,
        "window_seconds": 10,
        "block_seconds": 20,
        "overall": "FAIL",
    }

    try:
        adapter_log = (LOG_DIR / "day21-adapter-process.log").open("w")
        opened_logs.append(adapter_log)
        adapter = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "scripts/enforcement/day21_test_enforcer.py")],
            cwd=REPO_ROOT, env=env, stdout=adapter_log,
            stderr=subprocess.STDOUT,
        )
        processes.append(adapter)
        adapter_health = wait_for_health(f"{ENFORCER_URL}/__enforcer_health", adapter)
        report["adapter_health"] = adapter_health

        wrapper_log = (LOG_DIR / "day21-wrapper-process.log").open("w")
        opened_logs.append(wrapper_log)
        wrapper = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "scripts/enforcement/fail_open_wrapper.py")],
            cwd=REPO_ROOT, env=env, stdout=wrapper_log,
            stderr=subprocess.STDOUT,
        )
        processes.append(wrapper)
        wrapper_health = wait_for_health(f"{WRAPPER_URL}/__wrapper_health", wrapper)
        report["wrapper_health"] = wrapper_health

        # Start legitimate traffic first, then launch the attack during its run.
        traffic_env = env.copy()
        traffic_env["BILLING_OVERRIDE_URL"] = WRAPPER_URL
        traffic_log = (LOG_DIR / "day21-traffic-process.log").open("w")
        opened_logs.append(traffic_log)
        traffic = subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/traffic/traffic_generator.py"),
                "--duration", str(DURATION_SECONDS),
                "--seed", "21",
                "--graceful-stop",
                "--output-dir", str(traffic_dir),
                "--base-url", "http://127.0.0.1",
            ],
            cwd=REPO_ROOT, env=traffic_env,
            stdout=traffic_log, stderr=subprocess.STDOUT,
        )
        processes.append(traffic)
        time.sleep(1)

        attack_env = env.copy()
        attack_env["BILLING_OVERRIDE_URL"] = WRAPPER_URL
        attack_log = (LOG_DIR / "day21-attack-process.log").open("w")
        opened_logs.append(attack_log)
        attack = subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/attacks/bola_attack.py"),
                "--mode", "sweep",
                "--start-id", "1",
                "--end-id", "40",
                "--delay", "0.01",
                "--timeout", "3",
                "--output-dir", str(attack_dir),
            ],
            cwd=REPO_ROOT, env=attack_env,
            stdout=attack_log, stderr=subprocess.STDOUT,
        )
        processes.append(attack)

        traffic_return = traffic.wait(timeout=DURATION_SECONDS + 45)
        attack_return = attack.wait(timeout=45)
        report["traffic_process_exit_code"] = traffic_return
        report["attack_process_exit_code"] = attack_return

        if traffic_return != 0:
            raise RuntimeError(
                f"Traffic generator failed; inspect {LOG_DIR / 'day21-traffic-process.log'}"
            )
        if attack_return != 0:
            raise RuntimeError(
                f"BOLA sweep failed; inspect {LOG_DIR / 'day21-attack-process.log'}"
            )

        traffic_log_path = newest_traffic_log(traffic_dir)
        if traffic_log_path is None:
            raise RuntimeError("No traffic_*.jsonl file was produced")

        legitimate_records = read_jsonl(traffic_log_path)
        # The generator logs all its own requests as legitimate, including
        # authentication and read-only actions, not just billing requests.
        legitimate_count = len(legitimate_records)
        failures = [
            row for row in legitimate_records
            if not isinstance(row.get("status_code"), int)
            or row.get("status_code", 0) < 200
            or row.get("status_code", 0) >= 400
        ]
        success_count = legitimate_count - len(failures)

        stats_response = requests.get(
            f"{ENFORCER_URL}/__day21_stats", timeout=2
        )
        stats_response.raise_for_status()
        stats = stats_response.json()

        report.update({
            "traffic_log": str(traffic_log_path.relative_to(REPO_ROOT)),
            "legitimate_request_count": legitimate_count,
            "legitimate_success_count": success_count,
            "legitimate_failure_count": len(failures),
            "legitimate_success_rate": (
                success_count / legitimate_count if legitimate_count else 0.0
            ),
            "legitimate_failure_samples": failures[:10],
            "attacker_request_count": stats.get("attack_requests", 0),
            "attacker_blocked_count": stats.get("attack_blocked", 0),
            "legitimate_forwarded_count": stats.get("legitimate_forwarded", 0),
            "upstream_errors": stats.get("upstream_errors", 0),
            "enforcement_was_active": (
                stats.get("attack_blocked", 0) > 0
                and stats.get("evidence_type") == "application_layer_simulation"
            ),
            "adapter_stats": stats,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        evaluate_report(report)

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report.setdefault("finished_at", datetime.now(timezone.utc).isoformat())
        evaluate_report(report)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for stream in opened_logs:
            stream.close()

        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2))
        print(f"\nReport written to: {REPORT_PATH}")

    return 0 if report.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(run())
