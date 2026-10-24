
"""Concurrent, local-only API-Sentinel multi-threat simulation."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT.parent / "docker-compose.yml"

SERVICES = {
    "auth": "http://127.0.0.1:5001/health",
    "user": "http://127.0.0.1:5002/health",
    "order": "http://127.0.0.1:5003/health",
    "billing": "http://127.0.0.1:5004/health",
}

RECEIVER_HEALTH = "http://127.0.0.1:5099/health"
EXPECTED_INGESTION_SHUTDOWN = "intentional_orchestrator_cleanup"


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )


def jsonl_integrity(path):
    """Count valid JSON objects and malformed/non-object JSONL records."""
    path = Path(path)
    result = {
        "path": str(path),
        "lines": 0,
        "valid_objects": 0,
        "errors": [],
    }

    if not path.exists():
        result["errors"].append("file_missing")
        return result

    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue

                result["lines"] += 1

                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("JSON record is not an object")
                    result["valid_objects"] += 1
                except (json.JSONDecodeError, ValueError) as exc:
                    result["errors"].append(
                        {"line": line_number, "error": str(exc)}
                    )
    except OSError as exc:
        result["errors"].append(f"file_read_error: {exc}")

    return result


def health_snapshot():
    """Take one health sample across all four API services."""
    sample = {"timestamp": now(), "services": {}}

    for name, url in SERVICES.items():
        try:
            response = requests.get(url, timeout=1.5)
            sample["services"][name] = {
                "status_code": response.status_code,
                "healthy": response.status_code == 200,
            }
        except requests.RequestException as exc:
            sample["services"][name] = {
                "status_code": None,
                "healthy": False,
                "error": str(exc),
            }

    return sample


def validate_health_samples(
    path,
    negative_test=False,
    billing_outage_recovered=None,
    billing_final_health=None,
):
    """Validate health-monitor records and the expected outage scenario."""
    result = {
        "status": "FAIL",
        "sample_count": 0,
        "unhealthy_observations": {},
        "billing_outage_observed": False,
        "billing_recovered": False,
        "errors": [],
    }

    path = Path(path)

    if not path.exists():
        result["errors"].append("health_samples_missing")
        return result

    samples = []

    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue

                try:
                    sample = json.loads(line)
                except json.JSONDecodeError as exc:
                    result["errors"].append(
                        f"invalid_health_json_line_{line_number}: {exc}"
                    )
                    continue

                if not isinstance(sample, dict):
                    result["errors"].append(
                        f"health_record_not_object_line_{line_number}"
                    )
                    continue

                samples.append(sample)

    except OSError as exc:
        result["errors"].append(f"health_samples_unreadable: {exc}")
        return result

    result["sample_count"] = len(samples)

    if not samples:
        result["errors"].append("no_health_samples")
        return result

    required = set(SERVICES)
    observed = set()
    unhealthy = {name: 0 for name in required}

    for sample in samples:
        services = sample.get("services", {})

        if not isinstance(services, dict):
            result["errors"].append("invalid_services_object")
            continue

        observed.update(services)

        for name in required:
            if name not in services:
                continue

            service_status = services[name]

            if (
                not isinstance(service_status, dict)
                or service_status.get("healthy") is not True
            ):
                unhealthy[name] += 1

    result["unhealthy_observations"] = dict(sorted(unhealthy.items()))

    missing = required - observed
    if missing:
        result["errors"].append(
            f"missing_service_observations: {sorted(missing)}"
        )

    result["billing_outage_observed"] = unhealthy["billing"] > 0

    if negative_test:
        result["billing_recovered"] = (
            billing_outage_recovered is True
            and billing_final_health == "healthy"
        )

        if not result["billing_outage_observed"]:
            result["errors"].append("billing_outage_not_observed")

        if not result["billing_recovered"]:
            result["errors"].append("billing_recovery_not_confirmed")

        # Only billing is expected to be unhealthy during the deliberate
        # outage. Fail if another service is unhealthy at any sample.
        for name in required - {"billing"}:
            if unhealthy[name]:
                result["errors"].append(
                    f"unexpected_unhealthy_observations_{name}"
                )
    elif any(unhealthy.values()):
        result["errors"].append("unexpected_unhealthy_observations")

    if not result["errors"]:
        result["status"] = "PASS"

    return result


def wait_healthy(url, timeout=25):
    """Wait for an HTTP health endpoint to return status 200."""
    deadline = time.monotonic() + timeout
    last_error = "not responding"

    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)

        time.sleep(0.5)

    raise RuntimeError(f"{url} did not become healthy: {last_error}")


def compose(*args, timeout=45):
    """Run a Docker Compose command and raise on failure."""
    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        *args,
    ]

    return subprocess.run(
        command,
        cwd=ROOT.parent,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=True,
    )


def collect_billing_evidence(run_dir, started_at):
    """Collect billing logs and run the independent BOLA detector."""
    raw_path = run_dir / "billing_container_logs.txt"
    events_path = run_dir / "billing_events.jsonl"
    alerts_path = run_dir / "bola_detection_alerts.jsonl"
    summary_path = run_dir / "bola_detection_summary.json"

    result = {
        "status": "FAIL",
        "log_collection": "NOT_RUN",
        "events_file": str(events_path),
        "alerts_file": str(alerts_path),
        "summary_file": str(summary_path),
        "errors": [],
    }

    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "logs",
        "--since",
        started_at,
        "--timestamps",
        "billing",
    ]

    collected = None

    try:
        collected = subprocess.run(
            command,
            cwd=ROOT.parent,
            text=True,
            capture_output=True,
            timeout=45,
        )

        raw_path.write_text(
            collected.stdout + collected.stderr,
            encoding="utf-8",
        )

        if collected.returncode != 0:
            result["errors"].append(
                f"billing_log_collection_exit_{collected.returncode}"
            )
        else:
            result["log_collection"] = "OK"

        parsed = []
        malformed = 0

        for line in collected.stdout.splitlines():
            brace = line.find("{")
            if brace < 0:
                continue

            try:
                record = json.loads(line[brace:])
            except json.JSONDecodeError:
                malformed += 1
                continue

            if (
                isinstance(record, dict)
                and record.get("service") == "billing-service"
            ):
                parsed.append(record)

        with events_path.open("w", encoding="utf-8") as output:
            for record in parsed:
                output.write(json.dumps(record) + "\n")

        result["structured_events_collected"] = len(parsed)
        result["unparsed_json_lines"] = malformed

    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"billing_log_collection_error: {exc}")
        events_path.write_text("", encoding="utf-8")

    # Run detection even when collection fails so that evidence and a
    # detector summary are still generated. Collection failures remain fatal.
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))

        from scripts.detection.bola_detector import detect_file

        detection = detect_file(events_path, alerts_path)
        result["detector"] = detection

        if (
            result["log_collection"] == "OK"
            and detection.get("alerts_generated", 0) > 0
            and not detection.get("errors")
            and not result["errors"]
        ):
            result["status"] = "PASS"
        else:
            result["status"] = "FAIL"

    except Exception as exc:
        result["errors"].append(f"detector_error: {exc}")
        alerts_path.write_text("", encoding="utf-8")
        result["status"] = "ERROR"

    write_json(summary_path, result)
    return result


def preserve_scanner_outputs(run_dir):
    """Back up existing scanner outputs before running the scanner."""
    logs = ROOT / "logs"
    saved = {}

    for name in ("discovery_scan.jsonl", "discovery_report.json"):
        original = logs / name

        if original.exists():
            backup = run_dir / "preexisting_scanner_outputs" / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, backup)
            saved[name] = backup
        else:
            saved[name] = None

    return saved


def restore_scanner_outputs(saved):
    """Restore scanner outputs to their original state."""
    logs = ROOT / "logs"

    for name, backup in saved.items():
        original = logs / name

        if backup is None:
            original.unlink(missing_ok=True)
        else:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, original)


def evaluate_run(report):
    """Calculate the final result from all required run-level checks."""
    components = report.get("components", {})
    component_errors = []

    for name in ("forwarder", "traffic", "bola", "scanner"):
        component = components.get(name, {})

        if component.get("exit_code") != 0:
            component_errors.append(f"{name}_exit_not_zero")

    ingestion = components.get("ingestion", {})

    # The ingestion process is deliberately terminated during cleanup.
    # Its exit code can therefore be nonzero (for example, SIGTERM).
    # Validate that this shutdown was intentional and recorded instead.
    if ingestion.get("shutdown_reason") != EXPECTED_INGESTION_SHUTDOWN:
        component_errors.append("ingestion_shutdown_not_recorded")

    if ingestion.get("exit_code") is None:
        component_errors.append("ingestion_exit_code_missing")

    if report.get("negative_test"):
        if report.get("billing_outage_recovered") is not True:
            component_errors.append("billing_recovery_failed")

        if report.get("billing_final_health") != "healthy":
            component_errors.append("billing_final_health_failed")

    errors = list(report.get("errors", []))
    errors.extend(component_errors)

    pipeline_audit = report.get("pipeline_audit", {})
    bola_detection = report.get("bola_detection", {})

    checks = {
        "pipeline_audit": (
            pipeline_audit.get("status") == "PASS"
            and pipeline_audit.get("exit_code", 0) == 0
        ),
        "bola_detection": bola_detection.get("status") == "PASS",
        "components": not component_errors,
        "jsonl_integrity": (
            report.get("jsonl_integrity_status") == "PASS"
        ),
        "health": (
            report.get("health_validation", {}).get("status") == "PASS"
        ),
        "errors": not errors,
    }

    validation = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "errors": errors,
    }

    return validation


def run_once(args, run_dir, induce_outage=False):
    """Execute one concurrent simulation and produce its evidence report."""
    run_dir.mkdir(parents=True, exist_ok=False)

    sent_file = run_dir / "sent_requests.jsonl"
    sent_file.touch()

    captures = run_dir / "captures.jsonl"
    stop_file = run_dir / "forwarder.stop"
    health_file = run_dir / "health_samples.jsonl"

    report = {
        "started_at": now(),
        "run_directory": str(run_dir),
        "negative_test": induce_outage,
        "components": {},
        "health_samples": str(health_file),
        "errors": [],
        "billing_outage_recovered": None,
        "billing_final_health": None,
    }

    handles = {}
    processes = {}
    receiver = None
    scanner_saved = preserve_scanner_outputs(run_dir)

    health_stop = threading.Event()
    monitor_errors = []

    def monitor_health():
        try:
            with health_file.open("a", encoding="utf-8") as handle:
                while not health_stop.is_set():
                    handle.write(json.dumps(health_snapshot()) + "\n")
                    handle.flush()
                    health_stop.wait(2)
        except Exception as exc:
            monitor_errors.append(str(exc))

    monitor = threading.Thread(
        target=monitor_health,
        daemon=True,
        name="api-health-monitor",
    )

    def start_process(name, command, env=None):
        log_path = run_dir / f"{name}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        handles[name] = log_handle

        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except Exception:
            log_handle.close()
            handles.pop(name, None)
            raise

        processes[name] = process
        report["components"][name] = {
            "command": command,
            "log": str(log_path),
            "started": now(),
        }

        return process

    outage_started = False
    outage_recovered = False

    try:
        # Refuse to use an existing receiver so we do not interfere with
        # another pipeline or write to another run's capture file.
        try:
            response = requests.get(RECEIVER_HEALTH, timeout=1)
        except requests.ConnectionError:
            pass
        except requests.Timeout as exc:
            raise RuntimeError(
                "Port 5099 is occupied or unresponsive."
            ) from exc
        else:
            raise RuntimeError(
                "Port 5099 already has an HTTP receiver "
                f"(health returned {response.status_code}). Stop it first."
            )

        env = os.environ.copy()
        env["CAPTURES_PATH"] = str(captures.resolve())
        env["MOCK_DROP_RATE"] = "0"

        receiver_log = (run_dir / "ingestion.log").open(
            "w",
            encoding="utf-8",
        )
        handles["ingestion"] = receiver_log

        receiver_command = [
            sys.executable,
            "scripts/pipeline/mock_ingestion_pipeline.py",
        ]

        try:
            receiver = subprocess.Popen(
                receiver_command,
                cwd=ROOT,
                env=env,
                stdout=receiver_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except Exception:
            receiver_log.close()
            handles.pop("ingestion", None)
            raise

        report["components"]["ingestion"] = {
            "command": receiver_command,
            "log": str(run_dir / "ingestion.log"),
            "started": now(),
        }

        wait_healthy(RECEIVER_HEALTH)

        for url in SERVICES.values():
            wait_healthy(url)

        monitor.start()

        # Tail the fresh request file while legitimate traffic is generated.
        start_process(
            "forwarder",
            [
                sys.executable,
                "scripts/pipeline/mock_packet_forwarder.py",
                "--source",
                str(sent_file),
                "--receiver",
                "http://127.0.0.1:5099/capture",
                "--follow",
                "--duration",
                "600",
                "--poll-interval",
                "0.1",
                "--stop-file",
                str(stop_file),
            ],
        )

        start_process(
            "traffic",
            [
                sys.executable,
                "scripts/traffic/traffic_generator.py",
                "--duration",
                str(args.duration),
                "--output-dir",
                str(run_dir),
                "--base-url",
                args.base_url,
                "--seed",
                str(args.seed),
            ],
        )

        start_process(
            "bola",
            [
                sys.executable,
                "scripts/attacks/bola_attack.py",
                "--mode",
                "sweep",
                "--base-url",
                args.base_url,
                "--start-id",
                "1",
                "--end-id",
                str(args.bola_end_id),
                "--delay",
                str(args.bola_delay),
                "--timeout",
                "3",
                "--output-dir",
                str(run_dir),
            ],
        )

        start_process(
            "scanner",
            [
                sys.executable,
                "scripts/recon/endpoint_scanner.py",
                "--delay",
                str(args.scanner_delay),
            ],
        )

        started = time.monotonic()

        while any(
            processes[name].poll() is None
            for name in ("traffic", "bola", "scanner")
        ):
            elapsed = time.monotonic() - started

            if (
                induce_outage
                and not outage_started
                and elapsed >= max(2.0, args.duration / 2)
            ):
                compose("stop", "billing")
                outage_started = True
                report["billing_outage_started_at"] = now()

                time.sleep(4)

                try:
                    compose("start", "billing")
                    wait_healthy(SERVICES["billing"], timeout=35)
                    outage_recovered = True
                    report["billing_recovered_at"] = now()
                except Exception as exc:
                    report["errors"].append(
                        f"Billing recovery failed: {exc}"
                    )
                    # Continue to cleanup so billing is restarted in finally.
                    break

            time.sleep(0.2)

        # Stop any remaining workload processes if recovery failed or
        # orchestration ended early.
        for name in ("traffic", "bola", "scanner"):
            process = processes.get(name)
            if process is not None and process.poll() is None:
                process.terminate()

            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        # Let the forwarder drain the request file before stopping it.
        stop_file.touch()

        forwarder = processes.get("forwarder")
        if forwarder is not None:
            try:
                forwarder.wait(timeout=30)
            except subprocess.TimeoutExpired:
                forwarder.terminate()
                try:
                    forwarder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    forwarder.kill()
                    forwarder.wait(timeout=5)

        if induce_outage:
            report["billing_outage_recovered"] = outage_recovered

    except Exception as exc:
        report["errors"].append(f"simulation_error: {exc}")

    finally:
        # Always attempt to restore billing after a negative test.
        if induce_outage:
            try:
                compose("start", "billing")
                wait_healthy(SERVICES["billing"], timeout=35)
                report["billing_final_health"] = "healthy"
            except Exception as exc:
                report["billing_final_health"] = "recovery_failed"
                report["errors"].append(
                    f"Final billing recovery failed: {exc}"
                )

        health_stop.set()

        if monitor.is_alive():
            monitor.join(timeout=5)

        if monitor_errors:
            report["errors"].extend(
                f"health_monitor_error: {error}"
                for error in monitor_errors
            )

        # Clean up every launched child process and record its exit code.
        for name, process in processes.items():
            if process.poll() is None:
                process.terminate()

                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

            report["components"].setdefault(name, {})
            report["components"][name]["exit_code"] = process.returncode
            report["components"][name]["finished"] = now()

        # Ingestion is intentionally stopped by this orchestrator. Record
        # that fact rather than treating SIGTERM as a workload failure.
        if receiver is not None:
            if receiver.poll() is None:
                receiver.terminate()

            try:
                receiver.wait(timeout=5)
            except subprocess.TimeoutExpired:
                receiver.kill()
                receiver.wait(timeout=5)

            report["components"]["ingestion"].update(
                {
                    "exit_code": receiver.returncode,
                    "finished": now(),
                    "shutdown_reason": EXPECTED_INGESTION_SHUTDOWN,
                }
            )

        for handle in handles.values():
            try:
                handle.close()
            except OSError:
                pass

        # Preserve this run's scanner evidence before restoring prior files.
        for name in ("discovery_scan.jsonl", "discovery_report.json"):
            generated = ROOT / "logs" / name
            destination = run_dir / name

            if generated.exists():
                shutil.copy2(generated, destination)

        restore_scanner_outputs(scanner_saved)

    # Independently collect billing logs and evaluate BOLA evidence.
    # Keep this separate from the pipeline capture audit.
    try:
        report["bola_detection"] = collect_billing_evidence(
            run_dir,
            report["started_at"],
        )
    except Exception as exc:
        report["bola_detection"] = {
            "status": "ERROR",
            "errors": [str(exc)],
        }
        report["errors"].append(f"bola_evidence_error: {exc}")

    # Run the capture audit only after the forwarder has stopped.
    audit_path = run_dir / "audit_report.json"
    audit_cmd = [
        sys.executable,
        "scripts/pipeline/pipeline_audit.py",
        "--sent-source",
        str(sent_file),
        "--captures-source",
        str(captures),
        "--output",
        str(audit_path),
    ]

    try:
        audit_result = subprocess.run(
            audit_cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )

        (run_dir / "audit.log").write_text(
            audit_result.stdout + audit_result.stderr,
            encoding="utf-8",
        )

        report["audit_exit_code"] = audit_result.returncode

        if audit_path.exists():
            try:
                report["pipeline_audit"] = json.loads(
                    audit_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                report["pipeline_audit"] = {
                    "status": "ERROR",
                    "error": str(exc),
                    "exit_code": audit_result.returncode,
                }
        else:
            report["pipeline_audit"] = {
                "status": "ERROR",
                "exit_code": audit_result.returncode,
            }

        if audit_result.returncode != 0:
            report["errors"].append(
                f"pipeline_audit_exit_{audit_result.returncode}"
            )

    except (OSError, subprocess.SubprocessError) as exc:
        report["audit_exit_code"] = None
        report["pipeline_audit"] = {
            "status": "ERROR",
            "error": str(exc),
        }
        report["errors"].append(f"pipeline_audit_error: {exc}")

    # Check every required JSONL artifact, including health samples and
    # detector outputs. A missing artifact is a failed integrity check.
    report["jsonl_integrity"] = {
        "sent_requests": jsonl_integrity(sent_file),
        "captures": jsonl_integrity(captures),
        "bola": jsonl_integrity(run_dir / "bola_attack.jsonl"),
        "discovery": jsonl_integrity(run_dir / "discovery_scan.jsonl"),
        "health_samples": jsonl_integrity(health_file),
        "billing_events": jsonl_integrity(
            run_dir / "billing_events.jsonl"
        ),
        "bola_alerts": jsonl_integrity(
            run_dir / "bola_detection_alerts.jsonl"
        ),
    }

    report["jsonl_integrity_status"] = (
        "PASS"
        if all(
            not item["errors"]
            for item in report["jsonl_integrity"].values()
        )
        else "FAIL"
    )

    report["health_validation"] = validate_health_samples(
        health_file,
        negative_test=induce_outage,
        billing_outage_recovered=report.get("billing_outage_recovered"),
        billing_final_health=report.get("billing_final_health"),
    )

    report["finished_at"] = now()
    report["validation"] = evaluate_run(report)

    write_json(run_dir / "multi_threat_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bola-end-id", type=int, default=40)
    parser.add_argument("--bola-delay", type=float, default=0.03)
    parser.add_argument("--scanner-delay", type=float, default=0.05)
    parser.add_argument(
        "--output-root",
        default="logs/multi_threat_runs",
    )
    parser.add_argument(
        "--negative-test",
        action="store_true",
        help=(
            "Run a billing outage scenario, restore billing, "
            "then run normally"
        ),
    )

    args = parser.parse_args()

    if args.base_url != "http://127.0.0.1":
        parser.error("--base-url must be http://127.0.0.1 (local lab only)")

    if args.duration <= 0 or args.bola_end_id < 1:
        parser.error("--duration and --bola-end-id must be positive")

    if args.bola_delay < 0 or args.scanner_delay < 0:
        parser.error("delays cannot be negative")

    output_root = (ROOT / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    reports = []
    runs = [("normal", False)]

    if args.negative_test:
        runs = [
            ("negative", True),
            ("normal_after_negative", False),
        ]

    for label, induce_outage in runs:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = output_root / f"{stamp}_{label}"

        print(f"\n=== Starting {label} simulation: {run_dir} ===")

        try:
            report = run_once(
                args,
                run_dir,
                induce_outage=induce_outage,
            )
        except Exception as exc:
            # Preserve the summary even if an unexpected orchestration
            # exception escapes run_once.
            report = {
                "run_directory": str(run_dir),
                "pipeline_audit": {"status": "ERROR"},
                "bola_detection": {"status": "ERROR"},
                "jsonl_integrity_status": "FAIL",
                "health_validation": {"status": "FAIL"},
                "validation": {
                    "status": "FAIL",
                    "checks": {},
                    "errors": [f"unhandled_run_error: {exc}"],
                },
                "errors": [f"unhandled_run_error: {exc}"],
            }

            if run_dir.exists():
                write_json(run_dir / "multi_threat_report.json", report)

        audit = report.get("pipeline_audit", {})
        bola = report.get("bola_detection", {})
        validation = report.get("validation", {})

        summary_item = {
            "run_directory": str(run_dir),
            "pipeline_audit_status": audit.get("status", "MISSING"),
            "capture_rate_percent": audit.get("capture_rate_percent"),
            "bola_detection_status": bola.get("status", "MISSING"),
            "bola_alerts_generated": bola.get(
                "detector", {}
            ).get("alerts_generated", 0),
            "health_status": report.get(
                "health_validation", {}
            ).get("status", "MISSING"),
            "jsonl_integrity_status": report.get(
                "jsonl_integrity_status", "MISSING"
            ),
            "component_status": validation.get(
                "checks", {}
            ).get("components", False),
            "run_status": validation.get("status", "FAIL"),
            "errors": report.get("errors", []),
            "validation_errors": validation.get("errors", []),
        }

        reports.append(summary_item)
        print(json.dumps(summary_item, indent=2))

    summary = {
        "generated_at": now(),
        "runs": reports,
        "all_audits_passed": all(
            item["pipeline_audit_status"] == "PASS"
            for item in reports
        ),
        "all_bola_detections_passed": all(
            item["bola_detection_status"] == "PASS"
            for item in reports
        ),
        "all_runs_passed": all(
            item["run_status"] == "PASS"
            for item in reports
        ),
    }

    write_json(output_root / "multi_threat_report.json", summary)

    print(f"\nSummary: {output_root / 'multi_threat_report.json'}")
    print(f"Overall status: { 'PASS' if summary['all_runs_passed'] else 'FAIL' }")

    return 0 if summary["all_runs_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
