#!/usr/bin/env python3
"""End-to-end Phase 2 audit validation for API-Sentinel.

Exit code:
  0: every validation step passed
  1: one or more validation steps failed

This script intentionally does not remove Docker volumes.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
APPSEC = ROOT / "appsec-testing"
SCRIPTS = APPSEC / "scripts"
LOGS = APPSEC / "logs"
BASE = "http://127.0.0.1"

SERVICES = {
    "auth": f"{BASE}:5001/health",
    "user": f"{BASE}:5002/health",
    "order": f"{BASE}:5003/health",
    "billing": f"{BASE}:5004/health",
}

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = LOGS / f"phase2-run-{STAMP}"
REPORT_PATH = LOGS / "phase2_freeze_report.json"
results = []


def run_command(name, args, *, cwd=APPSEC, timeout=120):
    """Run a command and retain its combined output in this run's directory."""
    log_path = RUN_DIR / (name.lower().replace(" ", "_") + ".log")
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        log_path.write_text(proc.stdout or "", encoding="utf-8")
        return {
            "returncode": proc.returncode,
            "log": str(log_path),
            "output_tail": (proc.stdout or "")[-2500:],
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        log_path.write_text(str(output), encoding="utf-8")
        return {
            "returncode": None,
            "log": str(log_path),
            "output_tail": str(output)[-2500:],
            "error": f"Timed out after {timeout}s",
        }
    except OSError as exc:
        return {
            "returncode": None,
            "log": str(log_path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def step(name, fn):
    """Run one step, capture failures, and continue so the report is complete."""
    print(f"\n{'=' * 72}\nSTEP: {name}\n{'=' * 72}")
    started = time.monotonic()

    try:
        detail = fn() or {}
        passed = True
        error = None
    except Exception as exc:
        passed = False
        error = f"{type(exc).__name__}: {exc}"
        detail = {}

    elapsed = round(time.monotonic() - started, 2)
    entry = {
        "step": name,
        "passed": passed,
        "duration_s": elapsed,
        "error": error,
        "detail": detail,
    }
    results.append(entry)

    print(f"-> {'PASS' if passed else 'FAIL'} ({elapsed}s)")
    if error:
        print(f"   {error}")
    if detail:
        print(json.dumps(detail, indent=2, default=str))

    return passed


def read_json(path):
    path = Path(path)
    if not path.is_file():
        raise AssertionError(f"Expected JSON report does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"Cannot parse JSON report {path}: {exc}") from exc


def read_jsonl(path):
    path = Path(path)
    if not path.is_file():
        raise AssertionError(f"Expected JSONL evidence does not exist: {path}")

    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Invalid JSON on line {number} of {path}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise AssertionError(f"JSONL line {number} is not an object: {path}")
        records.append(record)

    if not records:
        raise AssertionError(f"No evidence records found in {path}")
    return records


def step_rebuild():
    """Rebuild/recreate containers without deleting persistent volumes."""
    result = run_command(
        "rebuild_stack",
        ["docker", "compose", "up", "--build", "-d"],
        cwd=ROOT,
        timeout=300,
    )
    if result["returncode"] != 0:
        raise AssertionError(f"Compose rebuild failed: {result}")

    return {
        "command": "docker compose up --build -d",
        "persistent_volumes_deleted": False,
        **result,
    }


def step_health():
    deadline = time.monotonic() + 45
    last = {}

    while time.monotonic() < deadline:
        all_ok = True
        last = {}

        for service, url in SERVICES.items():
            try:
                response = requests.get(url, timeout=3)
                try:
                    body = response.json()
                except ValueError:
                    body = {}

                last[service] = {
                    "status_code": response.status_code,
                    "body": body,
                }
                if response.status_code != 200 or body.get("status") != "ok":
                    all_ok = False
            except requests.RequestException as exc:
                last[service] = {"error": str(exc)}
                all_ok = False

        if all_ok:
            return {"services": last}

        time.sleep(1)

    raise AssertionError(f"Services did not all become healthy within 45s: {last}")


def step_bola():
    evidence_dir = RUN_DIR / "bola"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "bola_attack.jsonl"

    result = run_command(
        "bola_attack",
        [
            sys.executable,
            str(SCRIPTS / "attacks" / "bola_attack.py"),
            "--mode", "sweep",
            "--start-id", "1",
            "--end-id", "60",
            "--output-dir", str(evidence_dir),
        ],
        timeout=90,
    )
    if result["returncode"] != 0:
        raise AssertionError(f"BOLA attack command failed: {result}")

    records = read_jsonl(evidence_path)
    successes = [
        item for item in records
        if item.get("verdict", item.get("label")) == "BOLA_SUCCESS"
    ]
    if not successes:
        raise AssertionError(
            f"No BOLA_SUCCESS records in {evidence_path}; "
            "check whether the intentional lab vulnerability is still present."
        )

    cross_user = [
        item for item in successes
        if item.get("cross_user_access") is True
    ]
    if not cross_user:
        raise AssertionError(
            "BOLA success records exist, but none explicitly confirms "
            "cross_user_access=true."
        )

    return {
        "evidence": str(evidence_path),
        "records": len(records),
        "bola_successes": len(successes),
        "confirmed_cross_user_access": len(cross_user),
        "sample": cross_user[0],
        "command": result,
    }


def step_privesc():
    evidence_dir = RUN_DIR / "privesc"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "privesc_attack.jsonl"

    result = run_command(
        "privilege_escalation",
        [
            sys.executable,
            str(SCRIPTS / "attacks" / "privesc_attack.py"),
            "--output-dir", str(evidence_dir),
        ],
        timeout=60,
    )
    if result["returncode"] != 0:
        raise AssertionError(f"Privilege escalation command failed: {result}")

    records = read_jsonl(evidence_path)
    escalations = [
        item for item in records
        if item.get("verdict", item.get("label")) == "ESCALATION_SUCCESS"
    ]

    if len(records) != 8:
        raise AssertionError(
            f"Expected 8 matrix records (4 vectors x 2 targets), found {len(records)}."
        )
    if len(escalations) != 1:
        raise AssertionError(
            f"Expected exactly one escalation, found {len(escalations)}."
        )

    finding = escalations[0]
    if finding.get("target") != "billing" or finding.get("vector") != "path_id":
        raise AssertionError(
            f"Unexpected escalation location; expected billing/path_id: {finding}"
        )

    return {
        "evidence": str(evidence_path),
        "matrix_records": len(records),
        "escalation_count": len(escalations),
        "confirmed_location": "billing/path_id",
        "finding": finding,
        "command": result,
    }


def step_shadow_zombie():
    """Check all seven manifest routes without requiring every route to return 200."""
    checks = [
        ("auth", "GET", "/debug/dump-tokens", {200}),
        ("auth", "GET", "/api/v1/login-status", {200, 401, 403}),
        ("user", "GET", "/internal/config", {200}),
        ("user", "GET", "/api/v1/users/1", {200, 401, 403}),
        ("order", "GET", "/api/v1/orders/1", {200, 401, 403}),
        ("billing", "POST", "/_admin/reset-cache", {200}),
        ("billing", "GET", "/api/v1/invoices/1", {200, 401, 403}),
    ]

    observed = []
    failures = []

    for service, method, path, allowed in checks:
        port = {"auth": 5001, "user": 5002, "order": 5003, "billing": 5004}[service]
        url = f"{BASE}:{port}{path}"

        try:
            response = requests.request(method, url, timeout=5)
            item = {
                "service": service,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "allowed_statuses": sorted(allowed),
            }
            observed.append(item)
            if response.status_code not in allowed:
                failures.append(item)
        except requests.RequestException as exc:
            failures.append({
                "service": service,
                "method": method,
                "path": path,
                "error": str(exc),
            })

    if failures:
        raise AssertionError(f"Unreachable or unexpected planted endpoints: {failures}")

    return {"endpoints_checked": len(observed), "results": observed}


def step_discovery_scanner():
    report_path = LOGS / "discovery_report.json"

    # The scanner writes this shared default report path. Preserve any
    # pre-existing report in this run's evidence directory before replacing it.
    previous_copy = RUN_DIR / "previous_discovery_report.json"
    if report_path.exists():
        shutil.copy2(report_path, previous_copy)

    result = run_command(
        "discovery_scanner",
        [
            sys.executable,
            str(SCRIPTS / "recon" / "endpoint_scanner.py"),
            "--delay", "0.02",
        ],
        timeout=90,
    )
    if result["returncode"] != 0:
        raise AssertionError(f"Discovery scanner failed: {result}")

    report = read_json(report_path)
    total = report.get("total_discovered")
    if not isinstance(total, int) or total < 7:
        raise AssertionError(
            f"Expected scanner to discover at least 7 endpoints, got {total!r}."
        )

    by_service = report.get("by_service", {})
    required = {
        ("auth", "/debug/dump-tokens"),
        ("auth", "/api/v1/login-status"),
        ("user", "/internal/config"),
        ("user", "/api/v1/users/1"),
        ("order", "/api/v1/orders/1"),
        ("billing", "/_admin/reset-cache"),
        ("billing", "/api/v1/invoices/1"),
    }
    found = {
        (service, path)
        for service, paths in by_service.items()
        if isinstance(paths, list)
        for path in paths
    }
    missing = sorted(required - found)
    if missing:
        raise AssertionError(
            f"Scanner did not find all seven planted paths: {missing}; "
            f"report={report_path}"
        )

    return {
        "report": str(report_path),
        "total_discovered": total,
        "planted_paths_found": len(required - set(missing)),
        "planted_paths_expected": len(required),
        "command": result,
    }


def step_discovery_verifier():
    report_path = RUN_DIR / "discovery_verification_report.json"
    mock_path = SCRIPTS / "recon" / "mock_member3_discovery_output.json"
    manifest_path = APPSEC / "docs" / "shadow_zombie_manifest.md"
    day11_path = LOGS / "discovery_report.json"

    result = run_command(
        "discovery_verifier",
        [
            sys.executable,
            str(SCRIPTS / "recon" / "verify_discovery.py"),
            "--discovery-output", str(mock_path),
            "--manifest", str(manifest_path),
            "--day11-report", str(day11_path),
            "--out", str(report_path),
        ],
        timeout=20,
    )

    # A nonzero exit is expected for the deliberately imperfect mock.
    # The report itself must prove that grading behaved as designed.
    report = read_json(report_path)

    recall = report.get("recall")
    precision = report.get("precision")
    false_positive_count = report.get("false_positive_count")
    matched = report.get("matched_endpoints")
    ground_truth = report.get("ground_truth_endpoints")
    classification_errors = report.get("classification_error_count")
    validation_errors = report.get("validation_error_count")
    verdict = report.get("verdict")

    if not isinstance(recall, (int, float)) or abs(recall - (6 / 7)) > 0.01:
        raise AssertionError(f"Expected mock recall 6/7, got {recall!r}.")
    if not isinstance(precision, (int, float)) or abs(precision - (6 / 7)) > 0.01:
        raise AssertionError(f"Expected mock precision 6/7, got {precision!r}.")
    if false_positive_count != 1:
        raise AssertionError(f"Expected one mock false positive, got {false_positive_count!r}.")
    if matched != 6 or ground_truth != 7:
        raise AssertionError(
            f"Expected 6 matched of 7 ground-truth endpoints, got "
            f"{matched!r}/{ground_truth!r}."
        )
    if classification_errors != 0 or validation_errors != 0:
        raise AssertionError(
            "Mock should have no schema or classification errors; "
            f"got classification={classification_errors}, validation={validation_errors}."
        )
    if verdict != "FAIL":
        raise AssertionError(
            f"The deliberately imperfect mock should receive verdict FAIL, got {verdict!r}."
        )
    if result["returncode"] != 1:
        raise AssertionError(
            "Verifier CLI should exit 1 for the deliberately imperfect mock; "
            f"got {result['returncode']}."
        )

    return {
        "report": str(report_path),
        "mock_verdict": verdict,
        "recall": recall,
        "precision": precision,
        "matched_endpoints": matched,
        "ground_truth_endpoints": ground_truth,
        "false_positive_count": false_positive_count,
        "classification_errors": classification_errors,
        "validation_errors": validation_errors,
        "expected_mock_failure_confirmed": True,
        "real_member3_engine": "PENDING",
    }


def step_multi_threat():
    output_root = LOGS / f"phase2_multi_threat_{STAMP}"

    result = run_command(
        "multi_threat_simulation",
        [
            sys.executable,
            str(SCRIPTS / "simulation" / "multi_threat_simulation.py"),
            "--output-root", str(output_root),
        ],
        timeout=240,
    )

    summary_path = output_root / "multi_threat_report.json"
    summary = read_json(summary_path)

    if result["returncode"] != 0:
        raise AssertionError(
            f"Multi-threat simulation exited {result['returncode']}: "
            f"{result.get('output_tail', '')[-1500:]}"
        )

    if summary.get("all_runs_passed") is not True:
        raise AssertionError(f"all_runs_passed is not true: {summary}")

    if summary.get("all_audits_passed") is not True:
        raise AssertionError(f"all_audits_passed is not true: {summary}")

    if summary.get("all_bola_detections_passed") is not True:
        raise AssertionError(f"all_bola_detections_passed is not true: {summary}")

    return {
        "summary": str(summary_path),
        "all_runs_passed": summary["all_runs_passed"],
        "all_audits_passed": summary["all_audits_passed"],
        "all_bola_detections_passed": summary["all_bola_detections_passed"],
        "runs": summary.get("runs", []),
    }


def step_pytest():
    result = run_command(
        "pytest",
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=APPSEC,
        timeout=300,
    )
    if result["returncode"] != 0:
        raise AssertionError(f"Full pytest suite failed: {result}")

    tail = result.get("output_tail", "")
    summary = next(
        (line.strip() for line in reversed(tail.splitlines())
         if " passed" in line or " failed" in line),
        "pytest exited successfully; summary line not detected",
    )
    return {"command": result, "summary": summary}


def skip_step(name, reason):
    results.append({
        "step": name,
        "passed": False,
        "skipped": True,
        "duration_s": 0,
        "error": reason,
        "detail": {},
    })
    print(f"SKIP: {name} — {reason}")


def main():
    parser = argparse.ArgumentParser(
        description="Run the API-Sentinel Phase 2 audit validation."
    )
    parser.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=False)

    print("PHASE 2 FREEZE VALIDATION — Day 14")
    print(f"Repository: {ROOT}")
    print(f"Evidence directory: {RUN_DIR}")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("Safety: Docker volumes will not be deleted.")

    step("1. Rebuild containerized stack (preserve volumes)", step_rebuild)
    rebuild_ok = results[-1]["passed"]

    if rebuild_ok:
        step("2. All four API services healthy", step_health)
        health_ok = results[-1]["passed"]
    else:
        skip_step("2. All four API services healthy", "Stack rebuild failed")
        health_ok = False

    runtime_steps = [
        ("3. BOLA sweep confirms cross-user invoice access", step_bola),
        ("4. Privilege matrix has exactly one billing/path_id escalation", step_privesc),
        ("5. All seven planted shadow/zombie endpoints reachable", step_shadow_zombie),
        ("6. Scanner finds the planted discovery surface", step_discovery_scanner),
    ]

    if health_ok:
        for name, fn in runtime_steps:
            step(name, fn)
    else:
        for name, _ in runtime_steps:
            skip_step(name, "Runtime checks skipped because rebuild/health failed")

    # This verifier checks the deliberately imperfect mock and is independent
    # of API availability.
    step("7. Discovery grader correctly scores the imperfect mock", step_discovery_verifier)

    if health_ok:
        step("8. Multi-threat simulation passes", step_multi_threat)
        step("9. Full pytest suite passes", step_pytest)
    else:
        skip_step("8. Multi-threat simulation passes", "Runtime checks skipped because rebuild/health failed")
        skip_step("9. Full pytest suite passes", "Runtime checks skipped because rebuild/health failed")

    passed = sum(1 for item in results if item["passed"])
    skipped = sum(1 for item in results if item.get("skipped", False))
    failed = len(results) - passed - skipped
    all_passed = len(results) == 9 and passed == 9 and failed == 0 and skipped == 0

    report = {
        "project": "API-Sentinel",
        "milestone": "Phase 2 — Day 14 Audit Harness",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_result": "PASS" if all_passed else "FAIL",
        "summary": {
            "total_steps": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "run_directory": str(RUN_DIR),
        "real_member3_discovery_engine": "PENDING",
        "steps": results,
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n{'=' * 72}")
    print(f"OVERALL: {'PASS — Phase 2 validation passed' if all_passed else 'FAIL — DO NOT FREEZE'}")
    print(f"Steps: {passed} passed, {failed} failed, {skipped} skipped")
    for item in results:
        status = "x" if item["passed"] else ("-" if item.get("skipped") else " ")
        print(f"  [{status}] {item['step']} ({item['duration_s']}s)")
        if item["error"]:
            print(f"      ERROR: {item['error']}")
    print(f"Report: {REPORT_PATH}")
    print(f"Run evidence: {RUN_DIR}")

    if all_passed:
        print("Validation passed. Archive and freeze sign-off are separate steps.")
    else:
        print("Do not archive this report as passing evidence.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
