"""Day 16 detection tests. Live integration tests require the local Compose stack."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.detection import mock_detection_engine as engine

APPSEC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APPSEC_ROOT.parent
ENGINE_PATH = APPSEC_ROOT / "scripts/detection/mock_detection_engine.py"
GRADER_PATH = APPSEC_ROOT / "scripts/detection/realtime_flagging_test.py"
TRAFFIC_PATH = APPSEC_ROOT / "scripts/traffic/traffic_generator.py"
REQUIRED_SERVICES = {"auth", "user", "order", "billing"}


def event(requester=99, owner=10, cross_user=True, message="invoice accessed"):
    return json.dumps({
        "message": message,
        "requester_id": requester,
        "owner_id": owner,
        "cross_user_access": cross_user,
    })


def clear_detector():
    engine.access_history.clear()
    engine.already_alerted.clear()


def require_live_stack():
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--services", "--status", "running"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Cannot query the local Compose stack")

    if result.returncode != 0:
        pytest.skip("Docker Compose is unavailable")
    if not REQUIRED_SERVICES.issubset(set(result.stdout.split())):
        pytest.skip("Local API-Sentinel services are not all running")


def read_jsonl(path):
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def test_threshold_counts_distinct_owners_and_alerts_once(monkeypatch):
    clear_detector()
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 3)
    alerts = []
    monkeypatch.setattr(
        engine, "emit_alert",
        lambda requester, count: alerts.append((requester, count)),
    )

    for owner in (10, 20, 20, 30, 40):
        engine.process_log_line(event(owner=owner))

    assert alerts == [(99, 3)]


def test_repeated_owner_does_not_meet_threshold(monkeypatch):
    clear_detector()
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 3)
    alerts = []
    monkeypatch.setattr(
        engine, "emit_alert",
        lambda requester, count: alerts.append((requester, count)),
    )

    for owner in (10, 10, 20):
        engine.process_log_line(event(owner=owner))

    assert alerts == []


def test_own_data_and_unrelated_events_are_ignored(monkeypatch):
    clear_detector()
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 3)
    alerts = []
    monkeypatch.setattr(
        engine, "emit_alert",
        lambda requester, count: alerts.append((requester, count)),
    )

    for owner in (10, 20, 30):
        engine.process_log_line(event(owner=owner, cross_user=False))
    engine.process_log_line(event(owner=40, message="request"))
    engine.process_log_line("not-json")
    engine.process_log_line(json.dumps(["not", "an", "object"]))

    assert alerts == []
    assert not engine.access_history


def test_invalid_identifiers_are_ignored(monkeypatch):
    clear_detector()
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 1)
    alerts = []
    monkeypatch.setattr(
        engine, "emit_alert",
        lambda requester, count: alerts.append((requester, count)),
    )

    for requester, owner in (
        (True, 1), (0, 1), (1, True), (1, 0), ("1", 2)
    ):
        engine.process_log_line(event(requester=requester, owner=owner))

    assert alerts == []


def test_sliding_window_expires_old_entries(monkeypatch):
    clear_detector()
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 3)
    ticks = iter((0.0, 11.0, 12.0))
    monkeypatch.setattr(
        engine.time, "monotonic",
        lambda: next(ticks, 12.0),
    )
    alerts = []
    monkeypatch.setattr(
        engine, "emit_alert",
        lambda requester, count: alerts.append((requester, count)),
    )

    for owner in (10, 20, 30):
        engine.process_log_line(event(owner=owner))

    assert alerts == []


def test_live_attack_reaches_alert_target():
    require_live_stack()
    result = subprocess.run(
        [
            sys.executable, str(GRADER_PATH),
            "--timeout-seconds", "15",
            "--start-id", "1", "--end-id", "30", "--delay", "0",
        ],
        cwd=APPSEC_ROOT,
        capture_output=True,
        text=True,
        timeout=50,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr

    match = re.search(r"Report written to: (.+)", result.stdout)
    assert match, result.stdout
    report_path = Path(match.group(1).strip())
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["status"] == "PASS", report
    assert report["detection_latency_seconds"] <= 15
    assert report["cross_user_record_count"] >= 3


def test_live_legitimate_traffic_emits_no_alert(tmp_path):
    require_live_stack()
    alert_path = tmp_path / "legitimate_alerts.jsonl"
    engine_log_path = tmp_path / "mock_engine.log"
    traffic_dir = tmp_path / "legitimate_traffic"

    env = os.environ.copy()
    env["DETECTION_ALERTS_PATH"] = str(alert_path)
    env["DETECTION_WINDOW_SECONDS"] = "10"
    env["DETECTION_THRESHOLD"] = "3"
    env["DETECTION_LOG_LOOKBACK"] = datetime.now(timezone.utc).isoformat()

    with engine_log_path.open("w", encoding="utf-8") as engine_log:
        engine_proc = subprocess.Popen(
            [sys.executable, str(ENGINE_PATH)],
            cwd=APPSEC_ROOT,
            env=env,
            stdout=engine_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            ready = False
            while time.monotonic() < deadline:
                if engine_proc.poll() is not None:
                    break
                contents = engine_log_path.read_text(
                    encoding="utf-8", errors="replace"
                )
                if "MOCK detection engine started." in contents:
                    ready = True
                    break
                time.sleep(0.1)

            assert ready, engine_log_path.read_text(
                encoding="utf-8", errors="replace"
            )

            traffic = subprocess.run(
                [
                    sys.executable, str(TRAFFIC_PATH),
                    "--duration", "3",
                    "--min-delay", "0.05",
                    "--max-delay", "0.1",
                    "--output-dir", str(traffic_dir),
                    "--base-url", "http://127.0.0.1",
                    "--seed", "1616",
                    "--concurrency", "1",
                ],
                cwd=APPSEC_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
            assert traffic.returncode == 0, (
                traffic.stdout + "\n" + traffic.stderr
            )

            # Let the Compose log follower consume the final events.
            time.sleep(0.75)
            assert read_jsonl(alert_path) == []
        finally:
            if engine_proc.poll() is None:
                engine_proc.terminate()
                try:
                    engine_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    engine_proc.kill()
                    engine_proc.wait(timeout=3)


def test_engine_reports_docker_log_follower_failure(
    monkeypatch, tmp_path, capsys
):
    clear_detector()
    monkeypatch.setattr(engine, "ALERTS_PATH", tmp_path / "alerts.jsonl")

    captured = {}

    class FakeProcess:
        def __init__(self):
            import io

            self.stdout = io.StringIO("")
            self.returncode = 2

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    fake_process = FakeProcess()

    def fake_popen(command, **kwargs):
        captured["kwargs"] = kwargs
        return fake_process

    monkeypatch.setattr(engine.subprocess, "Popen", fake_popen)

    with pytest.raises(RuntimeError, match="status 2") as exc_info:
        engine.main()

    output = capsys.readouterr()

    assert captured["kwargs"]["stderr"] == subprocess.STDOUT
    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert "Docker Compose exit code: 2" in output.out
    assert (
        "Docker Compose log follower exited unexpectedly with status 2"
        in str(exc_info.value)
    )


def test_engine_reports_missing_docker_executable(monkeypatch, tmp_path):
    clear_detector()
    monkeypatch.setattr(engine, "ALERTS_PATH", tmp_path / "alerts.jsonl")

    def missing_docker(*args, **kwargs):
        raise FileNotFoundError("docker executable not found")

    monkeypatch.setattr(engine.subprocess, "Popen", missing_docker)

    with pytest.raises(RuntimeError, match="Could not start Docker Compose"):
        engine.main()


def test_engine_detects_exit_while_log_stream_is_silent(
    monkeypatch, tmp_path
):
    import threading

    clear_detector()
    monkeypatch.setattr(engine, "ALERTS_PATH", tmp_path / "alerts.jsonl")

    class SilentStream:
        def __init__(self):
            self.release = threading.Event()

        def __iter__(self):
            return self

        def __next__(self):
            # Simulate a log stream that remains open without producing lines.
            self.release.wait(timeout=5)
            raise StopIteration

        def close(self):
            self.release.set()

    class ExitedProcess:
        def __init__(self):
            self.stdout = SilentStream()
            self.returncode = 2

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.stdout.close()
            return self.returncode

        def terminate(self):
            pass

        def kill(self):
            self.stdout.close()

    fake_process = ExitedProcess()
    monkeypatch.setattr(
        engine.subprocess, "Popen", lambda *args, **kwargs: fake_process
    )

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="status 2"):
        engine.main()

    assert time.monotonic() - started < 2, (
        "Engine waited on a silent stream instead of detecting process exit"
    )


def test_qualifying_billing_event_writes_alert(monkeypatch, tmp_path):
    clear_detector()
    alert_path = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(engine, "ALERTS_PATH", alert_path)
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 1)

    engine.process_log_line(event(requester=99, owner=10, cross_user=True))

    alerts = read_jsonl(alert_path)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "cross_user_object_access"
    assert alerts[0]["requester_id"] == 99
    assert alerts[0]["distinct_owners_accessed"] == 1


def test_new_incident_alerts_after_sliding_window_expires(monkeypatch):
    clear_detector()
    monkeypatch.setattr(engine, "WINDOW_SECONDS", 10)
    monkeypatch.setattr(engine, "DISTINCT_OWNER_THRESHOLD", 2)

    ticks = iter((0.0, 1.0, 12.0, 13.0))
    monkeypatch.setattr(engine.time, "monotonic", lambda: next(ticks))

    alerts = []
    monkeypatch.setattr(
        engine, "emit_alert",
        lambda requester, count: alerts.append((requester, count)),
    )

    # First incident: two distinct owners trigger one alert.
    engine.process_log_line(event(requester=99, owner=10))
    engine.process_log_line(event(requester=99, owner=20))
    assert alerts == [(99, 2)]

    # Both earlier entries expire; the new incident should alert independently.
    engine.process_log_line(event(requester=99, owner=30))
    engine.process_log_line(event(requester=99, owner=40))
    assert alerts == [(99, 2), (99, 2)]
