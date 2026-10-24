"""Day 17 tests for bounded concurrent bot-traffic simulation."""
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "attacks" / "bot_traffic_generator.py"
sys.path.insert(0, str(ROOT / "scripts" / "attacks"))

import bot_traffic_generator as bot_generator  # noqa: E402
from bot_traffic_generator import (  # noqa: E402
    SafeAttackLogger,
    flood_worker,
    run_flood,
    validate_local_url,
)

AUTH_HEALTH = "http://127.0.0.1:5001/health"


def stack_is_up():
    try:
        return requests.get(AUTH_HEALTH, timeout=1).status_code == 200
    except requests.RequestException:
        return False


requires_stack = pytest.mark.skipif(
    not stack_is_up(), reason="local API-Sentinel stack is not running"
)


def read_records(output_dir):
    path = output_dir / "bot_traffic.jsonl"
    assert path.exists(), "expected bot_traffic.jsonl to be created"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_script(output_dir, *args):
    return subprocess.run(
        [
            sys.executable, str(SCRIPT), *args,
            "--output-dir", str(output_dir),
        ],
        capture_output=True,
        text=True,
        timeout=35,
    )


def test_only_local_project_targets_are_accepted():
    assert validate_local_url("http://127.0.0.1:5001/api/v2/auth/login")
    assert validate_local_url("http://localhost:5003/api/v2/orders")

    for target in (
        "https://127.0.0.1:5001/api/v2/auth/login",
        "http://example.com:5001/api/v2/auth/login",
        "http://127.0.0.1:5004/api/v2/auth/login",
        "http://127.0.0.1:5001/api/v2/auth/login?x=1",
    ):
        with pytest.raises(ValueError):
            validate_local_url(target)


def test_concurrent_logger_keeps_unique_sequence_numbers(tmp_path):
    from attack_logger import AttackLogger

    base_logger = AttackLogger("thread_test", output_dir=tmp_path)
    logger = SafeAttackLogger(base_logger)

    def write_many(worker):
        for index in range(25):
            logger.log(worker_id=worker, item=index, mode="test")

    try:
        with concurrent_executor() as pool:
            list(pool.map(write_many, range(8)))
    finally:
        base_logger.close()

    records = [
        json.loads(line)
        for line in (tmp_path / "thread_test.jsonl").read_text().splitlines()
    ]
    assert len(records) == 200
    assert sorted(record["attack_sequence"] for record in records) == list(range(200))


def concurrent_executor():
    from concurrent.futures import ThreadPoolExecutor
    return ThreadPoolExecutor(max_workers=8)


def test_flood_workers_execute_concurrently(monkeypatch):
    """Prove multiple workers reach request execution at the same time."""
    worker_count = 3
    barrier = threading.Barrier(worker_count)
    lock = threading.Lock()
    first_workers = set()

    def fake_request_and_log(session, logger, **kwargs):
        worker_id = kwargs["worker_id"]

        # Synchronize only each worker's first request. If run_flood were
        # sequential, the barrier would time out rather than pass.
        with lock:
            is_first_request = worker_id not in first_workers
            first_workers.add(worker_id)

        if is_first_request:
            barrier.wait(timeout=2)

        return {"status": 200, "success": True, "error": None}

    monkeypatch.setattr(
        bot_generator, "request_and_log", fake_request_and_log
    )

    total = run_flood(
        target_url="http://127.0.0.1:5003/api/v2/orders",
        method="GET",
        concurrency=worker_count,
        duration=0.05,
        logger=object(),
        run_id="unit-concurrency-test",
    )

    assert first_workers == set(range(worker_count))
    assert total >= worker_count


def test_flood_worker_stops_without_sending_requests():
    class FakeLogger:
        def log(self, **fields):
            raise AssertionError("stopped worker must not log a request")

    stop_event = threading.Event()
    stop_event.set()

    count = flood_worker(
        worker_id=0,
        target_url=AUTH_HEALTH,
        method="GET",
        duration=5,
        logger=FakeLogger(),
        stop_event=stop_event,
        run_id="unit-test",
    )
    assert count == 0


@requires_stack
def test_login_flood_writes_request_level_evidence(tmp_path):
    result = run_script(
        tmp_path,
        "--mode", "flood",
        "--target", "login",
        "--concurrency", "3",
        "--duration", "2",
    )
    assert result.returncode == 0, result.stderr

    records = read_records(tmp_path)
    assert records
    assert all(record["mode"] == "flood" for record in records)
    assert all(record["run_id"] for record in records)
    assert all(record["endpoint"] == "/api/v2/auth/login" for record in records)
    assert all("status" in record and "duration_ms" in record for record in records)
    assert all(record["worker_id"] in range(3) for record in records)
    assert len({record["attack_sequence"] for record in records}) == len(records)


@requires_stack
def test_credential_stuffing_logs_each_attempt_and_known_hits(tmp_path):
    result = run_script(
        tmp_path,
        "--mode", "creds_stuff",
        "--concurrency", "3",
        "--attempts-per-worker", "10",
        "--seed", "1701",
    )
    assert result.returncode == 0, result.stderr

    records = read_records(tmp_path)
    assert len(records) == 30
    assert all(record["mode"] == "creds_stuff" for record in records)
    assert all(record.get("username") for record in records)
    assert all(isinstance(record["success"], bool) for record in records)
    assert all(record["endpoint"] == "/api/v2/auth/login" for record in records)

    # Each worker's first attempt uses a real seeded username and demo password.
    # The service should accept these credentials in the healthy lab.
    assert sum(record["success"] for record in records) >= 3


def test_argument_bounds_reject_excessive_concurrency(tmp_path):
    result = run_script(
        tmp_path,
        "--mode", "flood",
        "--concurrency", "51",
        "--duration", "2",
    )
    assert result.returncode != 0
    assert "must not exceed 50" in result.stderr
    assert not (tmp_path / "bot_traffic.jsonl").exists()
