#!/usr/bin/env python3
"""Evaluate Phase 3 evidence and write a freeze-status report."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPSEC = ROOT / "appsec-testing"
LOGS = APPSEC / "logs"
DOCS = APPSEC / "docs"


def read_json(path):
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def relative(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def latest_report(pattern):
    """Select the newest matching report; never fall back to an older PASS."""
    candidates = list(LOGS.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def check_day15():
    path = APPSEC / "docs/day15-milestone-latency.md"
    content = read_text(path)

    if not content:
        return {
            "status": "UNVERIFIED",
            "source": relative(path),
            "reason": "Day 15 evidence document is missing.",
        }

    patterns = [
        r"observed aggregate P95 delta was\s*([0-9]+(?:\.[0-9]+)?)\s*ms",
        r"Observed P95 delta:\s*([0-9]+(?:\.[0-9]+)?)\s*ms",
    ]
    deltas = []
    for pattern in patterns:
        deltas.extend(
            float(value)
            for value in re.findall(pattern, content, re.IGNORECASE)
        )

    if not deltas:
        return {
            "status": "UNVERIFIED",
            "source": relative(path),
            "reason": "Could not extract explicitly recorded overhead deltas.",
        }

    passed = all(value < 5.0 for value in deltas)
    return {
        "status": "PASS" if passed else "FAIL",
        "source": relative(path),
        "target_ms": 5.0,
        "measured_deltas_ms": deltas,
        "reason": (
            "All recorded deltas meet the strict target."
            if passed
            else "Recorded benchmark deltas do not meet the strict <5 ms target."
        ),
    }


def check_phase1():
    path = ROOT / "docs/phase1-freeze-report.json"
    report = read_json(path)

    if report is None:
        return {
            "status": "UNVERIFIED",
            "source": relative(path),
            "reason": "Historical Phase 1 archive is unavailable.",
        }

    checks = report.get("checks")
    count = len(checks) if isinstance(checks, (dict, list)) else None
    status = report.get("status")

    return {
        "status": "HISTORICAL_PASS" if status == "PASS" else "UNVERIFIED",
        "source": relative(path),
        "reported_status": status,
        "check_count": count,
        "reason": "Historical archive only; not a fresh Phase 1 execution.",
    }


def check_phase2():
    doc_path = ROOT / "docs/phase2-freeze.md"
    report_path = LOGS / "phase2_freeze_report.json"

    content = read_text(doc_path)
    report = read_json(report_path)

    if report is not None:
        report_status = report.get(
            "overall_result", report.get("status", report.get("overall"))
        )
        if report_status == "PASS":
            return {
                "status": "PASS",
                "source": relative(report_path),
                "reason": "Machine-readable Phase 2 report records PASS.",
            }

    documented_pass = (
        re.search(r"\*\*Harness result:\*\*\s*PASS", content) is not None
        and re.search(r"\|\s*Total checks\s*\|\s*9\s*\|", content) is not None
        and re.search(r"\|\s*Passed\s*\|\s*9\s*\|", content) is not None
        and re.search(r"\|\s*Failed\s*\|\s*0\s*\|", content) is not None
        and re.search(r"\|\s*Skipped\s*\|\s*0\s*\|", content) is not None
    )

    if documented_pass:
        return {
            "status": "DOCUMENTED_PASS_UNVERIFIED",
            "source": relative(doc_path),
            "missing_report": relative(report_path),
            "reported_checks": {
                "total": 9, "passed": 9, "failed": 0, "skipped": 0
            },
            "reason": (
                "The document records 9/9 passing checks, but its "
                "machine-readable report is unavailable."
            ),
        }

    return {
        "status": "UNVERIFIED",
        "source": relative(doc_path),
        "reason": "Phase 2 machine report and documented pass could not be verified.",
    }


def check_day18():
    path = (
        LOGS / "day18_20261031_120756"
        / "rate_limit_effectiveness_report_rerun.json"
    )
    report = read_json(path)

    required = (
        "flood_blocking",
        "legitimate_success",
        "recovery",
        "negative_control",
    )

    checks = report.get("checks") if report else None
    checks = checks if isinstance(checks, dict) else {}
    results = {
        name: (
            isinstance(checks.get(name), dict)
            and checks[name].get("pass") is True
        )
        for name in required
    }
    passed = (
        report is not None
        and report.get("overall") == "PASS"
        and all(results.values())
    )

    return {
        "status": "TESTS_PASS" if passed else "FAIL" if report else "UNVERIFIED",
        "source": relative(path),
        "reported_overall": report.get("overall") if report else None,
        "checks": results,
        "reason": (
            "Fresh Day 18 runtime report and all four acceptance checks passed."
            if passed
            else "Day 18 report is missing or one or more acceptance checks failed."
        ),
    }


def check_day20():
    path = latest_report("fail_open_report_*.json")
    report = read_json(path) if path else None

    required = [
        "billing_preflight",
        "test_enforcer_started",
        "fail_closed_proxy_started",
        "wrapper_started",
        "fail_closed_proxy_enforces_when_available",
        "legitimate_traffic_through_enforcer",
        "legitimate_traffic_survives_enforcer_failure",
        "stopped_enforcer_negative_control",
        "test_enforcer_restarted",
        "enforcement_resumes_after_restart",
        "billing_remains_healthy",
    ]

    checks = report.get("checks") if report else None
    checks = checks if isinstance(checks, dict) else {}
    results = {
        name: (
            isinstance(checks.get(name), dict)
            and checks[name].get("passed") is True
        )
        for name in required
    }
    passed = (
        report is not None
        and report.get("overall") == "PASS"
        and report.get("required_checks") == required
        and all(results.values())
    )

    return {
        "status": (
            "SIMULATION_ONLY_RUNTIME_PASS"
            if passed
            else "SIMULATION_FAIL"
            if report and report.get("overall") == "FAIL"
            else "UNVERIFIED"
        ),
        "source": relative(path) if path else None,
        "reported_overall": report.get("overall") if report else None,
        "evidence_class": "application_layer_http_simulation",
        "checks": results,
        "reason": (
            "All Day 20 runtime checks passed; this is not TC/eBPF daemon "
            "fail-open proof."
            if passed
            else "Day 20 runtime report is missing or its required checks failed."
        ),
    }


def check_simulation_report(pattern, required_checks):
    path = latest_report(pattern)
    report = read_json(path) if path else None

    checks = report.get("checks") if report else None
    checks = checks if isinstance(checks, dict) else {}

    results = {
        name: checks.get(name) is True
        for name in required_checks
    }

    evidence_type = report.get("evidence_type") if report else None
    kernel_proof = report.get("kernel_drop_proof") if report else None

    passed = (
        report is not None
        and report.get("overall") == "PASS"
        and evidence_type == "application_layer_simulation"
        and kernel_proof is False
        and all(results.values())
    )

    return {
        "status": "SIMULATION_PASS" if passed else "SIMULATION_FAIL"
        if report and report.get("overall") == "FAIL" else "UNVERIFIED",
        "source": relative(path) if path else None,
        "reported_overall": report.get("overall") if report else None,
        "evidence_type": evidence_type,
        "kernel_drop_proof": kernel_proof,
        "checks": results,
        "reason": (
            "Runtime checks passed; application-layer evidence is not "
            "kernel-drop certification."
            if passed
            else "Latest report is missing, malformed, failed, or has "
            "incomplete acceptance checks."
        ),
    }


def main():
    day19_path = LOGS / "day19_kernel_drop_report.json"
    day23_path = LOGS / "day23_kernel_blocking_at_scale_report.json"
    day23_eval_path = LOGS / "day23_kernel_certification_report.json"

    day19 = read_json(day19_path)
    day23 = read_json(day23_path)
    day23_eval = read_json(day23_eval_path)

    day23_eval_checks = (
        day23_eval.get("checks") if day23_eval else None
    )
    day23_eval_checks = (
        day23_eval_checks if isinstance(day23_eval_checks, dict) else {}
    )

    required_day23_checks = (
        "day19_kernel_observation_valid",
        "day19_cleanup_complete",
        "day23_concurrency_cleanup_complete",
        "concurrency_workload_passed",
        "concurrent_kernel_drop_proof_present",
        "concurrent_source_port_evidence_valid",
        "concurrent_kernel_counters_valid",
        "concurrent_workload_totals_valid",
    )

    kernel_checks = {
        "day19_report_present": (
            day19 is not None and day19.get("overall") == "OBSERVED"
        ),
        "day23_report_present": (
            day23 is not None
            and day23.get("evidence_type") == "kernel_drop"
            and day23.get("kernel_drop_proof") is True
            and day23.get("concurrency_evidence") is True
        ),
        "day23_evaluation_present": day23_eval is not None,
        "day23_evaluation_passed": (
            day23_eval is not None
            and day23_eval.get("evidence_type") == "day23_evidence_evaluation"
            and day23_eval.get("kernel_certification") == "PASS"
            and day23_eval.get("overall") == "PASS"
            and day23_eval.get("kernel_drop_proof") is True
        ),
        "day23_all_evaluator_checks_passed": (
            all(day23_eval_checks.get(name) is True
                for name in required_day23_checks)
        ),
    }

    kernel_certification = (
        "PASS" if all(kernel_checks.values()) else "FAIL"
    )

    day15 = check_day15()
    phase1 = check_phase1()
    phase2 = check_phase2()
    day18 = check_day18()
    day20 = check_day20()

    day21 = check_simulation_report(
        "zero_drop_report_*.json",
        (
            "attacker_blocked",
            "enforcement_was_active",
            "legitimate_success_rate_is_100_percent",
            "legitimate_traffic_observed",
            "zero_legitimate_failures",
        ),
    )

    day22 = check_simulation_report(
        "mixed_stress_report_*.json",
        (
            "adversarial_block_rate_at_least_30_percent",
            "enforcement_adapter_active",
            "exact_adversarial_count",
            "exact_legitimate_count",
            "exact_workload_count",
            "latency_probes_observed",
            "legitimate_ratio_in_range",
            "legitimate_success_rate_at_least_98_percent",
            "resource_samples_observed",
            "resource_sampling_errors_absent",
            "zero_failed_latency_probes",
        ),
    )

    checks = {
        "phase1": phase1,
        "phase2": phase2,
        "day15": day15,
        "day18": day18,
        "day19": {
            "status": "OBSERVED" if kernel_checks["day19_report_present"]
            else "UNVERIFIED",
            "source": relative(day19_path),
            "reported_overall": day19.get("overall") if day19 else None,
        },
        "day20": day20,
        "day21": day21,
        "day22": day22,
        "day23": {
            "status": kernel_certification,
            "source": relative(day23_eval_path),
            "checks": kernel_checks,
        },
    }

    limitations = [
        "Day 15's recorded overhead measurements exceeded the strict <5 ms target.",
        "Day 20 is an application-layer fail-open simulation, not TC/eBPF daemon fail-open proof.",
        "Day 21 and Day 22 HTTP adapter results are application-layer simulations, not kernel-drop proof.",
        "Day 19 counters count packets and do not independently establish per-request blocking.",
        "Day 23 certifies the tested loopback TC/eBPF SYN-drop workload, not production-network reliability.",
        "Phase 2's documented pass cannot be independently checked because its machine-readable report is missing.",
    ]

    phase3_status = (
        "PASS"
        if (
            kernel_certification == "PASS"
            and day15["status"] == "PASS"
            and phase2["status"] == "PASS"
            and day18["status"] == "TESTS_PASS"
        )
        else "CONDITIONAL"
        if kernel_certification == "PASS"
        else "FAIL"
    )

    report = {
        "schema_version": 2,
        "evidence_type": "phase3_freeze_evaluation",
        "phase": "Phase 3",
        "kernel_certification": kernel_certification,
        "phase3_freeze_status": phase3_status,
        "checks": checks,
        "limitations": limitations,
        "read_only": True,
    }

    output = LOGS / "phase3_freeze_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nSaved Phase 3 report: {relative(output)}")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate API-Sentinel Phase 3 evidence and freeze status."
    )
    return parser.parse_args()


if __name__ == "__main__":
    parse_args()
    raise SystemExit(main())
