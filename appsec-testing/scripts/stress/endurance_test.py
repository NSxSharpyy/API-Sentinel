#!/usr/bin/env python3
"""Day 27: sustained endurance testing with durable checkpoints."""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = ROOT / "logs" / "day27"
CONTAINERS = {
    "auth": "api-sentinel-auth",
    "user": "api-sentinel-user",
    "order": "api-sentinel-order",
    "billing": "api-sentinel-billing",
}
DB_SERVICE = "order"
DB_PATH = "/app/data/shop.db"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_size_mib(value):
    """Convert a Docker memory quantity such as 34.66MiB or 3.789GiB to MiB."""
    match = re.fullmatch(
        r"\s*([0-9]+(?:\.[0-9]+)?)\s*(B|KiB|MiB|GiB|TiB)\s*",
        value,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Unsupported memory quantity: {value!r}")

    amount = float(match.group(1))
    unit = match.group(2).lower()
    factors = {
        "b": 1 / (1024 * 1024),
        "kib": 1 / 1024,
        "mib": 1,
        "gib": 1024,
        "tib": 1024 * 1024,
    }
    return amount * factors[unit]


def run_command(command, timeout=20):
    """Run a command and return stdout; raise a useful error on failure."""
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}: {message}"
        )
    return result.stdout


def sample_containers():
    """Return one CPU and memory sample per configured application container."""
    names = list(CONTAINERS.values())
    output = run_command([
        "docker", "stats", "--no-stream", "--format", "{{json .}}", *names
    ])

    rows = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        name = row.get("Container") or row.get("Name")
        if name not in names:
            continue

        cpu_text = str(row.get("CPUPerc", "")).strip().rstrip("%")
        cpu_percent = float(cpu_text)
        memory_text = str(row.get("MemUsage", "")).split("/", 1)[0].strip()

        alias = next(
            (key for key, container_name in CONTAINERS.items()
             if container_name == name),
            None,
        )
        if alias is None:
            continue

        rows[alias] = {
            "container_name": name,
            "cpu_percent": cpu_percent,
            "memory_mib": parse_size_mib(memory_text),
        }

    missing = sorted(set(CONTAINERS) - set(rows))
    if missing:
        raise RuntimeError(f"Docker stats omitted containers: {missing}")
    return rows


def sample_database_size():
    """Read the database file size inside the order container without modifying it."""
    output = run_command([
        "docker", "compose", "exec", "-T", DB_SERVICE,
        "python", "-c",
        (
            "import os; "
            f"p={DB_PATH!r}; "
            "print(os.path.getsize(p))"
        ),
    ])
    value = output.strip().splitlines()[-1]
    size = int(value)
    if size < 0:
        raise ValueError("Database size cannot be negative")
    return size


def append_checkpoint(path, record):
    """Append one checkpoint and force it to durable storage."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_checkpoints(path):
    """Read valid checkpoint rows; report malformed lines instead of hiding them."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint file not found: {path}")

    records = []
    malformed = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("checkpoint row must be a JSON object")
                records.append(record)
            except (json.JSONDecodeError, ValueError) as exc:
                malformed.append({"line": line_number, "error": str(exc)})

    return records, malformed


def validate_positive(value, name):
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"{name} must be a finite number > 0")
    return value


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run sustained API-Sentinel legitimate traffic and sample system health."
    )
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--sample-interval", type=float, default=60.0)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--seed", type=int, default=27)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Checkpoint JSONL path; defaults to OUTPUT_DIR/endurance_checkpoints.jsonl",
    )
    return parser




class RequestLogReader:
    """Incrementally read the Day4 sent-request JSONL log."""

    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.pending = b""
        self.total = 0
        self.failures = 0
        self.errors = {}
        self.latencies = []
        self.malformed_lines = 0

    def poll(self):
        if not self.path.exists():
            return

        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
            self.offset = handle.tell()

        data = self.pending + chunk
        lines = data.split(b"\n")
        self.pending = lines.pop()

        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
                if not isinstance(row, dict):
                    raise ValueError("request row is not an object")

                self.total += 1
                status = row.get("status_code")
                error = row.get("error")
                failed = bool(error)

                if status is None:
                    failed = True
                else:
                    try:
                        status = int(status)
                    except (TypeError, ValueError):
                        failed = True
                    else:
                        if not 200 <= status < 300:
                            failed = True

                if failed:
                    self.failures += 1
                    reason = str(error or f"http_{status}")
                    self.errors[reason] = self.errors.get(reason, 0) + 1

                latency = row.get("latency_ms")
                if latency is not None:
                    try:
                        latency = float(latency)
                        if math.isfinite(latency) and latency >= 0:
                            self.latencies.append(latency)
                    except (TypeError, ValueError):
                        pass

            except (json.JSONDecodeError, ValueError):
                self.malformed_lines += 1

    @staticmethod
    def percentile(values, percent):
        if not values:
            return None
        ordered = sorted(values)
        index = (len(ordered) - 1) * percent / 100
        lower = math.floor(index)
        upper = math.ceil(index)
        if lower == upper:
            return round(ordered[lower], 2)
        fraction = index - lower
        return round(
            ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 2
        )

    def snapshot(self):
        rate = (
            round(self.failures / self.total * 100, 4)
            if self.total else None
        )
        return {
            "total_requests": self.total,
            "failed_requests": self.failures,
            "error_rate_percent": rate,
            "latency_samples": len(self.latencies),
            "latency_p50_ms": self.percentile(self.latencies, 50),
            "latency_p95_ms": self.percentile(self.latencies, 95),
            "latency_p99_ms": self.percentile(self.latencies, 99),
            "error_types": dict(self.errors),
            "malformed_log_lines": self.malformed_lines,
        }


def linear_trend(points):
    """Return least-squares slope per hour for (elapsed_seconds, value)."""
    usable = [
        (float(x), float(y))
        for x, y in points
        if x is not None and y is not None
        and math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if len(usable) < 2:
        return None

    xs = [x / 3600 for x, _ in usable]
    ys = [y for _, y in usable]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None

    slope = sum(
        (x - mean_x) * (y - mean_y)
        for x, y in zip(xs, ys)
    ) / denominator
    return round(slope, 6)


def analyze_checkpoints(checkpoint_path, report_path, target_seconds=None):
    records, malformed = read_checkpoints(checkpoint_path)
    samples = [r for r in records if r.get("record_type") == "sample"]
    events = [r for r in records if r.get("record_type") == "event"]

    if not samples:
        raise ValueError("No valid sample records found in checkpoint file")

    samples.sort(key=lambda row: row.get("elapsed_seconds", 0))
    first = samples[0]
    last = samples[-1]
    observed_seconds = max(
        0.0,
        float(last.get("elapsed_seconds", 0))
        - float(first.get("elapsed_seconds", 0)),
    )

    container_trends = {}
    for alias in CONTAINERS:
        cpu_points = []
        memory_points = []
        for sample in samples:
            container = sample.get("containers", {}).get(alias, {})
            elapsed = sample.get("elapsed_seconds")
            cpu_points.append((elapsed, container.get("cpu_percent")))
            memory_points.append((elapsed, container.get("memory_mib")))

        container_trends[alias] = {
            "cpu_percent_per_hour": linear_trend(cpu_points),
            "memory_mib_per_hour": linear_trend(memory_points),
            "first_cpu_percent": cpu_points[0][1],
            "last_cpu_percent": cpu_points[-1][1],
            "first_memory_mib": memory_points[0][1],
            "last_memory_mib": memory_points[-1][1],
        }

    db_points = [
        (sample.get("elapsed_seconds"), sample.get("database_size_bytes"))
        for sample in samples
    ]

    latest_requests = next(
        (
            sample.get("request_metrics")
            for sample in reversed(samples)
            if isinstance(sample.get("request_metrics"), dict)
        ),
        {},
    )

    sampling_errors = [
        error
        for sample in samples
        for error in sample.get("sampling_errors", [])
    ]

    final_event = next(
        (event for event in reversed(events)
         if event.get("event") == "run_finished"),
        None,
    )
    interrupted_event = any(
        event.get("event") == "interrupted" for event in events
    )

    target_met = (
        target_seconds is not None
        and observed_seconds >= target_seconds
    )

    if interrupted_event:
        status = "INTERRUPTED"
    elif final_event and final_event.get("generator_exit_code") == 0 and target_met:
        status = "COMPLETED" if not sampling_errors and not malformed else "COMPLETED_WITH_WARNINGS"
    elif final_event:
        status = "INCOMPLETE"
    else:
        status = "RECOVERED_PARTIAL"

    report = {
        "day": 27,
        "title": "Sustained Endurance Stress Test",
        "generated_at": utc_now(),
        "status": status,
        "evidence_type": "legitimate_traffic_endurance",
        "target_duration_seconds": target_seconds,
        "observed_duration_seconds": round(observed_seconds, 2),
        "sample_count": len(samples),
        "checkpoint_count": len(records),
        "malformed_checkpoint_lines": malformed,
        "sampling_error_count": len(sampling_errors),
        "sampling_errors": sampling_errors,
        "request_metrics": latest_requests,
        "database": {
            "first_size_bytes": db_points[0][1],
            "last_size_bytes": db_points[-1][1],
            "size_bytes_per_hour": linear_trend(db_points),
        },
        "container_trends": container_trends,
        "generator_exit_code": (
            final_event.get("generator_exit_code") if final_event else None
        ),
        "interrupted": interrupted_event,
        "notes": [
            "A partial recovery report is not a six-hour completion certificate.",
            "Request error rate is derived from Day4 sent_requests.jsonl records.",
            "Container and database sampling errors are reported separately.",
            "Linear trends are descriptive and do not imply a pass threshold.",
        ],
    }

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(report_path)

    return report


def collect_sample(start_time, request_reader):
    elapsed = time.monotonic() - start_time
    errors = []
    containers = None
    database_size = None

    try:
        containers = sample_containers()
    except Exception as exc:
        errors.append({
            "component": "docker_stats",
            "error": f"{type(exc).__name__}: {exc}",
        })

    try:
        database_size = sample_database_size()
    except Exception as exc:
        errors.append({
            "component": "database_size",
            "error": f"{type(exc).__name__}: {exc}",
        })

    try:
        request_reader.poll()
    except Exception as exc:
        errors.append({
            "component": "request_log",
            "error": f"{type(exc).__name__}: {exc}",
        })

    return {
        "record_type": "sample",
        "timestamp": utc_now(),
        "elapsed_seconds": round(elapsed, 3),
        "containers": containers or {},
        "database_size_bytes": database_size,
        "request_metrics": request_reader.snapshot(),
        "sampling_errors": errors,
    }


def run_endurance(args):
    run_dir = args.output_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.checkpoint.resolve()
    report_path = run_dir / "endurance_report.json"
    traffic_dir = run_dir / "traffic"
    request_log = traffic_dir / "sent_requests.jsonl"

    if checkpoint.exists():
        raise FileExistsError(
            f"Checkpoint already exists: {checkpoint}. "
            "Choose a new --output-dir or --checkpoint; evidence will not be overwritten."
        )

    traffic_dir.mkdir(parents=True, exist_ok=True)
    duration_seconds = args.hours * 3600
    request_reader = RequestLogReader(request_log)
    start_time = time.monotonic()
    generator = None
    generator_exit = None
    interrupted = False

    generator_stdout = (run_dir / "generator.stdout.log").open("w", encoding="utf-8")
    generator_stderr = (run_dir / "generator.stderr.log").open("w", encoding="utf-8")

    command = [
        sys.executable,
        str(ROOT / "scripts" / "traffic" / "traffic_generator.py"),
        "--duration", str(duration_seconds),
        "--output-dir", str(traffic_dir),
        "--seed", str(args.seed),
        "--concurrency", str(args.concurrency),
        "--graceful-stop",
    ]

    append_checkpoint(checkpoint, {
        "record_type": "event",
        "event": "run_started",
        "timestamp": utc_now(),
        "target_duration_seconds": duration_seconds,
        "sample_interval_seconds": args.sample_interval,
        "generator_command": command,
    })

    try:
        generator = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=generator_stdout,
            stderr=generator_stderr,
        )

        next_sample = 0.0
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= duration_seconds:
                break

            if generator.poll() is not None:
                generator_exit = generator.returncode
                append_checkpoint(checkpoint, {
                    "record_type": "event",
                    "event": "generator_exited_early",
                    "timestamp": utc_now(),
                    "elapsed_seconds": round(elapsed, 3),
                    "generator_exit_code": generator_exit,
                })
                break

            if elapsed >= next_sample:
                record = collect_sample(start_time, request_reader)
                append_checkpoint(checkpoint, record)
                print(
                    f"Checkpoint at {elapsed:.0f}s | "
                    f"requests={record['request_metrics']['total_requests']} | "
                    f"errors={len(record['sampling_errors'])}",
                    flush=True,
                )
                next_sample += args.sample_interval

            remaining = min(
                max(0.1, next_sample - (time.monotonic() - start_time)),
                max(0.1, duration_seconds - (time.monotonic() - start_time)),
            )
            time.sleep(remaining)

    except KeyboardInterrupt:
        interrupted = True
        print("\nStop requested; asking traffic generator to stop gracefully.", flush=True)
        append_checkpoint(checkpoint, {
            "record_type": "event",
            "event": "interrupted",
            "timestamp": utc_now(),
            "elapsed_seconds": round(time.monotonic() - start_time, 3),
        })

    finally:
        if generator is not None and generator.poll() is None:
            try:
                if not interrupted:
                    # At the planned deadline, let the Day4 generator finish
                    # its in-flight customer cycle before requesting shutdown.
                    generator_exit = generator.wait(timeout=60)

                if generator_exit is None:
                    # Ctrl+C was requested, or natural shutdown exceeded its
                    # grace period. The Day4 generator handles SIGINT safely.
                    generator.send_signal(2)
                    generator_exit = generator.wait(timeout=30)

            except subprocess.TimeoutExpired:
                generator.terminate()
                try:
                    generator_exit = generator.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    generator.kill()
                    generator_exit = generator.wait()

        elif generator is not None:
            generator_exit = generator.returncode

        # Capture one final sample after the generator has stopped.
        final_sample = collect_sample(start_time, request_reader)
        append_checkpoint(checkpoint, final_sample)

        append_checkpoint(checkpoint, {
            "record_type": "event",
            "event": "run_finished",
            "timestamp": utc_now(),
            "elapsed_seconds": round(time.monotonic() - start_time, 3),
            "generator_exit_code": generator_exit,
            "interrupted": interrupted,
        })

        generator_stdout.close()
        generator_stderr.close()

    report = analyze_checkpoints(
        checkpoint,
        report_path,
        target_seconds=duration_seconds,
    )
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path),
        "checkpoint": str(checkpoint),
        "observed_duration_seconds": report["observed_duration_seconds"],
        "request_metrics": report["request_metrics"],
    }, indent=2))
    return 0 if report["status"] in {
        "COMPLETED", "COMPLETED_WITH_WARNINGS", "INTERRUPTED"
    } else 1


def main():
    parser = parse_args()
    args = parser.parse_args()

    if not math.isfinite(args.hours) or args.hours <= 0:
        parser.error("--hours must be a finite number > 0")
    if not math.isfinite(args.sample_interval) or args.sample_interval <= 0:
        parser.error("--sample-interval must be a finite number > 0")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")

    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.checkpoint = (
        args.checkpoint.resolve()
        if args.checkpoint
        else args.output_dir / "endurance_checkpoints.jsonl"
    )

    try:
        if args.analyze_only:
            report = analyze_checkpoints(
                args.checkpoint,
                args.output_dir / "endurance_report.json",
                target_seconds=args.hours * 3600,
            )
            print(json.dumps(report, indent=2))
            return 0

        return run_endurance(args)

    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Day27 error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
