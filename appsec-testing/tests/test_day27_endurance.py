"""Day 27 endurance runner: metrics, checkpoint, and recovery tests."""

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "stress"
    / "endurance_test.py"
)
SPEC = importlib.util.spec_from_file_location("day27_endurance", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_memory_units_are_normalized_to_mib():
    assert runner.parse_size_mib("34.66MiB") == pytest.approx(34.66)
    assert runner.parse_size_mib("3.789GiB") == pytest.approx(3879.936)
    assert runner.parse_size_mib("1024KiB") == pytest.approx(1.0)
    assert runner.parse_size_mib("1TiB") == pytest.approx(1048576.0)


def test_invalid_memory_unit_is_rejected():
    with pytest.raises(ValueError):
        runner.parse_size_mib("12MB")


def test_checkpoint_append_and_read_round_trip(tmp_path):
    path = tmp_path / "checkpoints.jsonl"
    record = {"record_type": "sample", "elapsed_seconds": 60}
    runner.append_checkpoint(path, record)

    records, malformed = runner.read_checkpoints(path)

    assert records == [record]
    assert malformed == []


def test_checkpoint_reader_reports_malformed_lines(tmp_path):
    path = tmp_path / "checkpoints.jsonl"
    path.write_text(
        '{"record_type":"sample"}\nnot-json\n',
        encoding="utf-8",
    )

    records, malformed = runner.read_checkpoints(path)

    assert len(records) == 1
    assert malformed == [{"line": 2, "error": "Expecting value: line 1 column 1 (char 0)"}]


def test_request_reader_counts_http_and_transport_errors(tmp_path):
    path = tmp_path / "sent_requests.jsonl"
    rows = [
        {"status_code": 200, "error": None, "latency_ms": 10},
        {"status_code": 503, "error": "ClientResponseError", "latency_ms": 20},
        {"status_code": 0, "error": "TimeoutError", "latency_ms": 30},
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    reader = runner.RequestLogReader(path)
    reader.poll()
    metrics = reader.snapshot()

    assert metrics["total_requests"] == 3
    assert metrics["failed_requests"] == 2
    assert metrics["error_rate_percent"] == pytest.approx(66.6667)
    assert metrics["error_types"]["ClientResponseError"] == 1
    assert metrics["error_types"]["TimeoutError"] == 1


def test_request_reader_handles_partial_line_until_completed(tmp_path):
    path = tmp_path / "sent_requests.jsonl"
    path.write_text('{"status_code":200,', encoding="utf-8")

    reader = runner.RequestLogReader(path)
    reader.poll()
    assert reader.snapshot()["total_requests"] == 0

    with path.open("a", encoding="utf-8") as handle:
        handle.write('"error":null,"latency_ms":5}\n')

    reader.poll()
    assert reader.snapshot()["total_requests"] == 1


def test_request_reader_counts_malformed_json_lines(tmp_path):
    path = tmp_path / "sent_requests.jsonl"
    path.write_text("not-json\n", encoding="utf-8")

    reader = runner.RequestLogReader(path)
    reader.poll()

    assert reader.snapshot()["malformed_log_lines"] == 1
    assert reader.snapshot()["total_requests"] == 0


def test_percentile_interpolates_between_values():
    assert runner.RequestLogReader.percentile([10, 20, 30, 40], 50) == 25
    assert runner.RequestLogReader.percentile([], 95) is None


def test_linear_trend_returns_slope_per_hour():
    assert runner.linear_trend([(0, 10), (3600, 20), (7200, 30)]) == 10
    assert runner.linear_trend([(0, 10)]) is None


def test_linear_trend_ignores_missing_values():
    assert runner.linear_trend([
        (0, 10),
        (3600, None),
        (7200, 30),
    ]) == 10


def test_recovery_analysis_builds_report_from_checkpoints(tmp_path):
    checkpoint = tmp_path / "endurance_checkpoints.jsonl"
    report_path = tmp_path / "endurance_report.json"

    samples = [
        {
            "record_type": "sample",
            "elapsed_seconds": 0,
            "containers": {
                "auth": {"cpu_percent": 10, "memory_mib": 30},
                "user": {"cpu_percent": 11, "memory_mib": 31},
                "order": {"cpu_percent": 12, "memory_mib": 32},
                "billing": {"cpu_percent": 13, "memory_mib": 33},
            },
            "database_size_bytes": 1000,
            "request_metrics": {"total_requests": 10, "failed_requests": 1},
            "sampling_errors": [],
        },
        {
            "record_type": "sample",
            "elapsed_seconds": 3600,
            "containers": {
                "auth": {"cpu_percent": 20, "memory_mib": 40},
                "user": {"cpu_percent": 21, "memory_mib": 41},
                "order": {"cpu_percent": 22, "memory_mib": 42},
                "billing": {"cpu_percent": 23, "memory_mib": 43},
            },
            "database_size_bytes": 2000,
            "request_metrics": {"total_requests": 100, "failed_requests": 2},
            "sampling_errors": [],
        },
    ]

    for sample in samples:
        runner.append_checkpoint(checkpoint, sample)

    report = runner.analyze_checkpoints(
        checkpoint, report_path, target_seconds=21600
    )

    assert report["status"] == "RECOVERED_PARTIAL"
    assert report["sample_count"] == 2
    assert report["request_metrics"]["total_requests"] == 100
    assert report["container_trends"]["auth"]["cpu_percent_per_hour"] == 10
    assert report["container_trends"]["auth"]["memory_mib_per_hour"] == 10
    assert report["database"]["size_bytes_per_hour"] == 1000
    assert json.loads(report_path.read_text())["status"] == "RECOVERED_PARTIAL"


def test_interrupted_run_is_not_reported_as_completed(tmp_path):
    checkpoint = tmp_path / "checkpoints.jsonl"
    runner.append_checkpoint(checkpoint, {
        "record_type": "sample",
        "elapsed_seconds": 0,
        "containers": {},
        "database_size_bytes": 100,
        "request_metrics": {},
        "sampling_errors": [],
    })
    runner.append_checkpoint(checkpoint, {
        "record_type": "event",
        "event": "interrupted",
    })

    report = runner.analyze_checkpoints(
        checkpoint, tmp_path / "report.json", target_seconds=21600
    )

    assert report["status"] == "INTERRUPTED"
    assert report["interrupted"] is True


def test_no_samples_prevents_report_generation(tmp_path):
    checkpoint = tmp_path / "checkpoints.jsonl"
    runner.append_checkpoint(checkpoint, {
        "record_type": "event",
        "event": "run_started",
    })

    with pytest.raises(ValueError, match="No valid sample"):
        runner.analyze_checkpoints(
            checkpoint, tmp_path / "report.json", target_seconds=21600
        )


def test_missing_checkpoint_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        runner.read_checkpoints(tmp_path / "missing.jsonl")


def test_container_sampler_returns_expected_aliases(monkeypatch):
    docker_rows = [
        {
            "Container": name,
            "CPUPerc": "10.0%",
            "MemUsage": "20MiB / 1GiB",
        }
        for name in runner.CONTAINERS.values()
    ]

    monkeypatch.setattr(
        runner,
        "run_command",
        lambda command, timeout=20: "\n".join(
            json.dumps(row) for row in docker_rows
        ),
    )

    result = runner.sample_containers()

    assert set(result) == {"auth", "user", "order", "billing"}
    assert result["auth"]["cpu_percent"] == 10.0
    assert result["auth"]["memory_mib"] == 20.0
