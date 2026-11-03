#!/usr/bin/env python3
"""Run the eight-segment API-Sentinel Day 30 demo rehearsal."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


APPSEC_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APPSEC_ROOT.parent
LOGS_ROOT = APPSEC_ROOT / "logs"
DAY23_SCALE_REPORT = LOGS_ROOT / "day23_kernel_blocking_at_scale_report.json"
DAY23_CERT_REPORT = LOGS_ROOT / "day23_kernel_certification_report.json"

DEFAULT_PORTS = {
    "AUTH_SERVICE_PORT": "5101",
    "USER_SERVICE_PORT": "5102",
    "ORDER_SERVICE_PORT": "5103",
    "BILLING_SERVICE_PORT": "5104",
}

HEALTH_ENDPOINTS = {
    "auth": "/health",
    "user": "/health",
    "order": "/health",
    "billing": "/health",
}

SERVICE_PORT_KEYS = {
    "auth": "AUTH_SERVICE_PORT",
    "user": "USER_SERVICE_PORT",
    "order": "ORDER_SERVICE_PORT",
    "billing": "BILLING_SERVICE_PORT",
}

SEGMENT_BUDGETS = {
    "platform_health": 90,
    "manual_bola": 60,
    "automated_bola": 90,
    "realtime_detection": 120,
    "kernel_evidence": 120,
    "fail_open": 60,
    "owasp_regression": 60,
    "closeout": 30,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def service_ports(env: dict[str, str]) -> dict[str, int]:
    result = {}
    for service, key in SERVICE_PORT_KEYS.items():
        raw = env.get(key, DEFAULT_PORTS[key])
        try:
            port = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid port in {key}: {raw!r}") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"Port out of range in {key}: {port}")
        result[service] = port
    return result


def check_health(env: dict[str, str], timeout: float = 3.0) -> dict:
    ports = service_ports(env)
    checks = {}
    for service, port in ports.items():
        url = f"http://127.0.0.1:{port}{HEALTH_ENDPOINTS[service]}"
        try:
            with urlopen(url, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                checks[service] = {
                    "healthy": response.status == 200,
                    "status_code": response.status,
                    "url": url,
                    "body": body[:1000],
                }
        except (URLError, TimeoutError, OSError) as exc:
            checks[service] = {
                "healthy": False,
                "url": url,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return {
        "overall": "PASS" if all(x["healthy"] for x in checks.values()) else "FAIL",
        "services": checks,
    }


def run_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: int,
    cwd: Path = APPSEC_ROOT,
    output_path: Path,
) -> dict:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = completed.stdout or ""
        status = "PASS" if completed.returncode == 0 else "FAIL"
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        captured = exc.stdout or ""
        if isinstance(captured, bytes):
            captured = captured.decode("utf-8", errors="replace")
        output = str(captured) + f"\nCOMMAND TIMED OUT after {timeout}s\n"
        status = "TIMEOUT"
        exit_code = None
    except OSError as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        status = "ERROR"
        exit_code = None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return {
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": command,
        "output_file": str(output_path),
        "output_tail": output[-4000:],
    }


def extract_path(output: str, pattern: str) -> Path | None:
    matches = re.findall(pattern, output, flags=re.MULTILINE)
    if not matches:
        return None
    candidate = Path(matches[-1].strip())
    if not candidate.is_absolute():
        candidate = APPSEC_ROOT / candidate
    return candidate


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL at {path}:{line_number}"
                ) from exc
            if not isinstance(item, dict):
                raise ValueError(
                    f"Expected JSON object at {path}:{line_number}"
                )
            records.append(item)
    return records


def free_tcp_port(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def segment_record(name: str, result: dict, started: float) -> dict:
    if "duration_seconds" in result:
        result["runner_duration_seconds"] = result["duration_seconds"]
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    result["budget_seconds"] = SEGMENT_BUDGETS[name]
    result["within_budget"] = (
        result["duration_seconds"] <= SEGMENT_BUDGETS[name]
    )
    return result


class Rehearsal:
    def __init__(self, run_number: int, run_dir: Path, base_env: dict[str, str]):
        self.run_number = run_number
        self.run_dir = run_dir
        self.base_env = base_env.copy()
        self.segments: dict[str, dict] = {}
        self.started_at = utc_now()

    def save_segment(self, name: str, started: float, result: dict) -> None:
        self.segments[name] = segment_record(name, result, started)

    def segment_health(self) -> bool:
        started = time.monotonic()
        result = check_health(self.base_env)
        result["service_ports"] = service_ports(self.base_env)
        result["status"] = result["overall"]
        self.save_segment("platform_health", started, result)
        return result["overall"] == "PASS"

    def segment_manual_bola(self) -> dict:
        started = time.monotonic()
        results = {}
        env = self.base_env.copy()
        output_dir = self.run_dir / "manual_bola"

        for invoice_id in (1, 5):
            evidence_dir = output_dir / f"invoice_{invoice_id}"
            command = [
                sys.executable,
                "scripts/attacks/bola_attack.py",
                "--mode", "targeted",
                "--username", "alice.anderson1",
                "--invoice-id", str(invoice_id),
                "--repeats", "1",
                "--delay", "0",
                "--output-dir", str(evidence_dir),
            ]
            result = run_command(
                command,
                env=env,
                timeout=25,
                output_path=output_dir / f"invoice_{invoice_id}.log",
            )
            evidence_path = evidence_dir / "bola_attack.jsonl"
            records = []
            if evidence_path.exists():
                records = read_jsonl(evidence_path)
            results[str(invoice_id)] = {
                **result,
                "evidence_file": str(evidence_path),
                "records": records,
            }

        passed = all(
            item["status"] == "PASS" and bool(item["records"])
            for item in results.values()
        )
        result = {
            "status": "PASS" if passed else "FAIL",
            "overall": "PASS" if passed else "FAIL",
            "attacker": "alice.anderson1",
            "invoice_results": results,
            "note": "Targeted manual demonstration; observed verdicts are taken from JSONL evidence.",
        }
        self.save_segment("manual_bola", started, result)
        return result

    def segment_automated_bola(self) -> dict:
        started = time.monotonic()
        output_dir = self.run_dir / "automated_bola"
        evidence_dir = output_dir / "evidence"
        command = [
            sys.executable,
            "scripts/attacks/bola_attack.py",
            "--mode", "sweep",
            "--start-id", "1",
            "--end-id", "50",
            "--delay", "0",
            "--output-dir", str(evidence_dir),
        ]
        result = run_command(
            command,
            env=self.base_env.copy(),
            timeout=75,
            output_path=output_dir / "bola_sweep.log",
        )
        evidence_path = evidence_dir / "bola_attack.jsonl"
        records = []
        evidence_error = None
        if evidence_path.exists():
            try:
                records = read_jsonl(evidence_path)
            except (OSError, ValueError) as exc:
                evidence_error = str(exc)

        compromised = [
            row for row in records
            if row.get("label") == "BOLA_SUCCESS"
            and row.get("cross_user_access") is True
        ]
        result.update({
            "evidence_file": str(evidence_path),
            "records_total": len(records),
            "compromised_invoice_count": len(compromised),
            "compromised_invoice_ids": [
                row.get("invoice_id") for row in compromised
            ],
            "evidence_error": evidence_error,
            "expected_range": [1, 50],
            "note": "Compromise count is measured from the run's own JSONL evidence; no expected count is hardcoded.",
        })
        if not records or evidence_error or not compromised:
            result["status"] = "FAIL"
            result["overall"] = "FAIL"
            if records and not compromised and not evidence_error:
                result["failure_reason"] = (
                    "No confirmed cross-user BOLA successes were recorded."
                )
        self.save_segment("automated_bola", started, result)
        return result

    def segment_detection(self) -> dict:
        started = time.monotonic()
        output_path = self.run_dir / "detection_runner.log"
        command = [
            sys.executable,
            "scripts/detection/realtime_flagging_test.py",
            "--timeout-seconds", "10",
            "--start-id", "1",
            "--end-id", "50",
            "--delay", "0",
        ]
        result = run_command(
            command,
            env=self.base_env.copy(),
            timeout=45,
            output_path=output_path,
        )
        report_path = extract_path(
            result.get("output_tail", "") + "\n" + output_path.read_text(
                encoding="utf-8"
            ),
            r"Report written to:\s*(.+)",
        )
        report = None
        report_error = None
        if report_path and report_path.exists():
            try:
                report = read_json(report_path)
            except (OSError, ValueError) as exc:
                report_error = str(exc)

        result.update({
            "report_file": str(report_path) if report_path else None,
            "report_status": report.get("status") if report else None,
            "detection_latency_seconds": (
                report.get("detection_latency_seconds") if report else None
            ),
            "distinct_cross_user_owners": (
                report.get("distinct_cross_user_owners") if report else []
            ),
            "mode": report.get("mode") if report else None,
            "failures": report.get("failures") if report else [],
            "report_error": report_error,
        })
        if (
            result["status"] != "PASS"
            or not report
            or report.get("status") != "PASS"
            or report.get("mode") != "MOCK DATA — TEMPORARY"
        ):
            result["status"] = "FAIL"
        self.save_segment("realtime_detection", started, result)
        return result

    def segment_kernel_evidence(self) -> dict:
        started = time.monotonic()
        checks = {}
        for label, path in (
            ("scale_report", DAY23_SCALE_REPORT),
            ("certification_report", DAY23_CERT_REPORT),
        ):
            try:
                data = read_json(path)
                checks[label] = {
                    "file": str(path),
                    "overall": data.get("overall"),
                    "evidence_type": data.get("evidence_type"),
                    "kernel_drop_proof": data.get("kernel_drop_proof"),
                    "concurrency_evidence": data.get("concurrency_evidence"),
                    "interface": data.get("interface"),
                    "destination_port": data.get("destination_port"),
                    "limitations": data.get("limitations"),
                }
            except (OSError, ValueError) as exc:
                checks[label] = {
                    "file": str(path),
                    "error": f"{type(exc).__name__}: {exc}",
                }

        scale = checks.get("scale_report", {})
        cert = checks.get("certification_report", {})
        passed = (
            scale.get("overall") == "PASS"
            and scale.get("evidence_type") == "kernel_drop"
            and scale.get("kernel_drop_proof") is True
            and scale.get("concurrency_evidence") is True
            and cert.get("overall") == "PASS"
            and cert.get("kernel_drop_proof") is True
        )
        result = {
            "status": "PASS" if passed else "FAIL",
            "evidence": checks,
            "qualification": (
                "Recorded Day 23 loopback TC/eBPF SYN-drop evidence. "
                "This does not establish production-interface or billing-service enforcement."
            ),
        }
        self.save_segment("kernel_evidence", started, result)
        return result

    def segment_fail_open(self) -> dict:
        started = time.monotonic()
        output_path = self.run_dir / "day20_fail_open.log"
        required_ports = (8004, 8005, 8006)
        unavailable = [
            port for port in required_ports if not free_tcp_port(port)
        ]
        if unavailable:
            result = {
                "status": "BLOCKED",
                "unavailable_ports": unavailable,
                "reason": "Day 20 verifier requires ports 8004, 8005, and 8006 to be free.",
            }
            self.save_segment("fail_open", started, result)
            return result

        env = self.base_env.copy()
        env.update({
            "DAY20_BILLING_URL": "http://127.0.0.1:5104",
            "DAY20_ENFORCER_UPSTREAM_URL": "http://127.0.0.1:5104",
            "DAY20_DIRECT_UPSTREAM_URL": "http://127.0.0.1:5104",
            "DAY20_ENFORCER_PORT": "8004",
            "DAY20_WRAPPER_PORT": "8005",
            "DAY20_FAIL_CLOSED_PORT": "8006",
        })
        command = [
            sys.executable,
            "scripts/enforcement/fail_open_verification.py",
        ]
        result = run_command(
            command,
            env=env,
            timeout=55,
            output_path=output_path,
        )
        output = output_path.read_text(encoding="utf-8")
        report_path = extract_path(
            output, r"Report written to:\s*(.+)"
        )
        report = None
        if report_path and report_path.exists():
            try:
                report = read_json(report_path)
            except (OSError, ValueError):
                report = None
        result.update({
            "report_file": str(report_path) if report_path else None,
            "report_overall": report.get("overall") if report else None,
            "evidence_type": "application_layer_simulation",
            "qualification": (
                "Day 20 fail-open behavior is an application-layer HTTP simulation, not kernel-drop evidence."
            ),
        })
        if not report or report.get("overall") != "PASS":
            result["status"] = "FAIL"
        self.save_segment("fail_open", started, result)
        return result

    def segment_owasp(self) -> dict:
        started = time.monotonic()
        output_dir = self.run_dir / "owasp"
        report_path = output_dir / "owasp_regression_report.json"
        command = [
            sys.executable,
            "scripts/compliance/owasp_top10_regression.py",
            "--timeout", "300",
            "--report", str(report_path),
        ]
        result = run_command(
            command,
            env=self.base_env.copy(),
            timeout=330,
            output_path=output_dir / "owasp_runner.log",
        )
        report = None
        try:
            report = read_json(report_path)
        except (OSError, ValueError):
            pass
        result.update({
            "report_file": str(report_path),
            "overall": report.get("overall") if report else None,
            "coverage": report.get("coverage") if report else None,
            "categories": report.get("categories") if report else None,
            "note": "OWASP category coverage is reported as classified by the regression runner; PARTIAL is not counted as COVERED.",
        })
        if not report or report.get("overall") == "FAIL":
            result["status"] = "FAIL"
        elif report.get("overall") == "PARTIAL":
            result["status"] = "PARTIAL"
        self.save_segment("owasp_regression", started, result)
        return result

    def segment_closeout(self) -> dict:
        started = time.monotonic()
        output_dir = self.run_dir / "closeout"
        compiled_path = output_dir / "day30-security-validation-summary.md"
        command = [
            sys.executable,
            "scripts/reporting/compile_report.py",
            "--root", str(APPSEC_ROOT),
            "--output", str(compiled_path),
        ]
        result = run_command(
            command,
            env=self.base_env.copy(),
            timeout=25,
            output_path=output_dir / "compile_report.log",
        )
        result.update({
            "compiled_report": str(compiled_path),
            "report_exists": compiled_path.is_file(),
        })
        if not compiled_path.is_file():
            result["status"] = "FAIL"
        self.save_segment("closeout", started, result)
        return result

    def run(self) -> dict:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        health_ok = self.segment_health()

        if health_ok:
            self.segment_manual_bola()
            self.segment_automated_bola()
            self.segment_detection()
            self.segment_kernel_evidence()
            self.segment_fail_open()
        else:
            for name in (
                "manual_bola",
                "automated_bola",
                "realtime_detection",
                "kernel_evidence",
                "fail_open",
            ):
                self.segments[name] = {
                    "status": "SKIPPED",
                    "reason": "Required application health checks did not pass.",
                    "budget_seconds": SEGMENT_BUDGETS[name],
                    "within_budget": True,
                }

        # Compliance and report compilation are useful even if live services fail.
        self.segment_owasp()
        self.segment_closeout()

        statuses = [item["status"] for item in self.segments.values()]
        failed = sum(status in ("FAIL", "ERROR", "TIMEOUT") for status in statuses)
        blocked = sum(status == "BLOCKED" for status in statuses)
        skipped = sum(status == "SKIPPED" for status in statuses)
        partial = sum(status == "PARTIAL" for status in statuses)
        passed = sum(status == "PASS" for status in statuses)

        report = {
            "day": 30,
            "run_number": self.run_number,
            "run_id": self.run_dir.name,
            "started_at_utc": self.started_at,
            "finished_at_utc": utc_now(),
            "overall": (
                "FAIL" if failed > 0
                else "PARTIAL" if blocked > 0 or skipped > 0 or partial > 0
                else "PASS"
            ),
            "summary": {
                "passed": passed,
                "partial": partial,
                "failed": failed,
                "blocked": blocked,
                "skipped": skipped,
                "segment_count": len(self.segments),
            },
            "segments": self.segments,
            "timing_budget_seconds": sum(SEGMENT_BUDGETS.values()),
            "timing_budget_note": (
                "630 seconds of segment budgets within a 720-second total presentation window."
            ),
        }
        write_json(self.run_dir / "rehearsal_report.json", report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output-root", type=Path, default=LOGS_ROOT / "day30_rehearsals")
    args = parser.parse_args()

    if not 1 <= args.runs <= 10:
        parser.error("--runs must be between 1 and 10")

    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = APPSEC_ROOT / output_root
    output_root.mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    for key, value in DEFAULT_PORTS.items():
        base_env.setdefault(key, value)
    base_env.setdefault("DETECTION_COMPOSE_CLI", "podman")

    reports = []
    for run_number in range(1, args.runs + 1):
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            + f"_run{run_number}_"
            + uuid.uuid4().hex[:8]
        )
        run_dir = output_root / run_id
        print(f"\n=== DAY 30 REHEARSAL {run_number}/{args.runs} ===")
        print(f"Evidence directory: {run_dir}")
        try:
            report = Rehearsal(run_number, run_dir, base_env).run()
        except Exception as exc:
            report = {
                "day": 30,
                "run_number": run_number,
                "run_id": run_id,
                "overall": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "rehearsal_report.json", report)
        reports.append(report)
        print(json.dumps({
            "run_id": run_id,
            "overall": report.get("overall"),
            "summary": report.get("summary"),
        }, indent=2))

    summary = {
        "day": 30,
        "created_at_utc": utc_now(),
        "requested_runs": args.runs,
        "completed_runs": len(reports),
        "runs": [
            {
                "run_id": report.get("run_id"),
                "overall": report.get("overall"),
                "report": str(output_root / report.get("run_id", "") / "rehearsal_report.json"),
            }
            for report in reports
        ],
        "all_passed": all(report.get("overall") == "PASS" for report in reports),
    }
    summary_path = output_root / (
        "day30_rehearsal_summary_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + ".json"
    )
    write_json(summary_path, summary)
    print(f"\nSummary: {summary_path}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
