#!/usr/bin/env python3
"""Compile verified API-Sentinel evidence into a Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Load a JSON object without allowing missing or invalid evidence to crash."""
    if not path.is_file():
        return None, "missing"

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"unreadable: {exc}"

    if not isinstance(value, dict):
        return None, "invalid: top-level JSON value is not an object"

    return value, "available"


def latest_json(directory: Path, pattern: str) -> Path | None:
    """Return the newest matching JSON file, using its path as a tie-breaker."""
    candidates = list(directory.glob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def display(value: Any, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def evidence_line(label: str, path: Path, data: dict | None, status: str) -> str:
    if data is None:
        return f"- **{label}:** Unavailable ({status}); source: `{path}`."
    return f"- **{label}:** Source `{path}`."


def discover_artifacts(root: Path) -> list[tuple[str, str]]:
    """Inventory every JSON log and Markdown document under the evidence folders."""
    artifacts: list[tuple[str, str]] = []

    for folder, pattern in ((root / "logs", "*.json"), (root / "docs", "*.md")):
        if not folder.is_dir():
            continue

        for path in sorted(folder.rglob(pattern)):
            relative = path.relative_to(root).as_posix()

            if pattern == "*.json":
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    status = (
                        "available"
                        if isinstance(value, dict)
                        else "invalid: top-level JSON value is not an object"
                    )
                except json.JSONDecodeError as exc:
                    status = f"invalid: malformed JSON: {exc}"
                except (OSError, UnicodeError) as exc:
                    status = f"unreadable: {exc}"
            else:
                try:
                    path.read_text(encoding="utf-8")
                    status = "available"
                except (OSError, UnicodeError) as exc:
                    status = f"unreadable: {exc}"

            artifacts.append((relative, status))

    return artifacts


def append_artifact_inventory(lines: list[str], root: Path) -> None:
    """Append a complete, status-aware inventory of discovered evidence files."""
    artifacts = discover_artifacts(root)
    counts = {
        "available": sum(status == "available" for _, status in artifacts),
        "unreadable": sum(status.startswith("unreadable:") for _, status in artifacts),
        "invalid": sum(status.startswith("invalid:") for _, status in artifacts),
    }

    lines.extend([
        "## 3.1 Complete evidence artifact inventory",
        "",
        "This inventory discovers every `logs/**/*.json` and `docs/**/*.md` "
        "file present when the report is compiled. Discovery does not mean "
        "that an artifact was independently validated or that its test passed.",
        "",
        f"- Discovered artifacts: **{len(artifacts)}**",
        f"- Readable/valid artifacts: **{counts['available']}**",
        f"- Unreadable artifacts: **{counts['unreadable']}**",
        f"- Invalid JSON artifacts: **{counts['invalid']}**",
        "",
        "| Artifact | Inventory status |",
        "|---|---|",
    ])

    if not artifacts:
        lines.append("| None found | Unavailable |")
    else:
        for relative, status in artifacts:
            safe_status = status.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{relative}` | {safe_status} |")

    lines.append("")


def append_latency_graphs(lines: list[str]) -> None:
    """Render documented latency values without conflating test populations."""
    lines.extend([
        "## 3.2 Latency comparisons",
        "",
        "### Day 5 — Aggregate and authenticated API P95",
        "",
        "The first two values are aggregate benchmark runs. The authenticated "
        "API-only result is a separate acceptance run and excludes bootstrap "
        "login latency.",
        "",
        "```mermaid",
        "xychart-beta",
        '    x-axis ["Initial aggregate", "10-VU aggregate", "Authenticated API"]',
        '    y-axis "P95 latency (ms)" 0 --> 130',
        "    bar [75.761, 117.511, 12.50]",
        "```",
        "",
        "Source: `docs/benchmark-baseline.md`. The bootstrap login P95 "
        "was 561.34 ms and is a separate diagnostic measurement, not included "
        "in the authenticated API P95.",
        "",
        "### Day 15 — Direct baseline versus mock sidecar",
        "",
        "```mermaid",
        "xychart-beta",
        '    x-axis ["Direct baseline", "Mock sidecar"]',
        '    y-axis "Aggregate P95 latency (ms)" 0 --> 130',
        "    bar [85.7661309, 122.430898]",
        "```",
        "",
        "- Observed aggregate P95 delta: **36.6647671 ms**.",
        "- Strict overhead target: **less than 5 ms — FAILED**.",
        "- Both aggregate P95 values also exceeded the separate 50 ms target.",
        "- This was a mock-sidecar comparison, not a real eBPF overhead measurement.",
        "",
        "Source: `docs/day15-milestone-latency.md` and "
        "`docs/day15-milestone-report-2026-10-21.md`.",
        "",
    ])


def build_report(root: Path) -> str:
    logs = root / "logs"
    docs = root / "docs"

    def read(relative: str) -> tuple[dict | None, str]:
        return load_json(root / relative)

    lines = [
            "# API-Sentinel Performance and Security Validation Report",
            "",
            "> Compiled from existing project evidence. This report does not represent",
            "> a new security test, production certification, or independent audit.",
            "",
            "## Executive summary",
            "",
            "The available evidence demonstrates functional security controls and",
            "controlled enforcement experiments in a local synthetic API environment.",
            "The evidence does not establish production readiness or complete security",
            "certification.",
            "",
            "- Day 5 authenticated API performance acceptance: PASS at 12.50 ms P95.",
            "- Day 5 original 10-VU aggregate baseline: P95 threshold FAILED at 117.511 ms.",
            "- Day 15 monitoring overhead: strict less-than-5-ms target FAILED.",
            "- Day 23 controlled loopback kernel-drop certification: PASS.",
            "- Phase 3 overall freeze: CONDITIONAL.",
            "- Day 26 OWASP regression coverage: PARTIAL at 57.14%.",
            "- Day 27 endurance status: see detailed evidence below.",
            "",
            "## Methodology",
            "",
            "- Compile existing JSON reports, Markdown documentation, and test files.",
            "- Preserve the scope and evidence type stated by each source.",
            "- Prefer recorded source values over inferred or reconstructed metrics.",
            "- Treat test definitions as evidence of coverage, not proof of historical execution.",
            "- Do not convert missing, malformed, skipped, or partial evidence into a pass.",
            "- Distinguish application-layer simulations from kernel packet-drop evidence.",
            "- Treat local synthetic results as lab observations, not production guarantees.",
            "",
            "## 1. Evidence handling",
            "",
            "- Metrics are read from existing reports or explicitly identified documentation.",
            "- Missing, malformed, or incomplete evidence is not treated as a pass.",
            "- Application-layer simulations are distinguished from kernel-drop evidence.",
            "- Controlled local-lab results are not presented as production guarantees.",
            "",
            "## 2. Verified milestone evidence",
            "",
        ]

    # Day 5: documented benchmark evidence.
    day5_doc = docs / "benchmark-baseline.md"
    lines.extend(["### Day 5 — Baseline performance benchmark", ""])

    if day5_doc.is_file():
        lines.extend([
            "- Source is the benchmark documentation; the referenced raw result "
            "files were not present in the inspected benchmark-results directory.",
            "- Initial 30-second baseline: 3,918 requests, 130.485 requests/s, "
            "average latency 14.814 ms, P95 75.761 ms, 0% HTTP failures, "
            "and 100% checks passed.",
            "- Official 10-VU, 30-second run: 2,838 requests, 93.050 requests/s, "
            "average latency 22.595 ms, P95 117.511 ms, and P99 219.393 ms.",
            "- The official aggregate P95 failed the required less-than-50-ms "
            "threshold. HTTP failures were 0% and checks passed 100%.",
            "- Login was the observed latency hotspot: average 115.889 ms and "
            "P95 231.775 ms.",
            "- Revised authenticated-only acceptance run: P95 12.50 ms, "
            "P99 20.39 ms, 0% HTTP failures, 0% custom errors, and 100% checks.",
            "- Bootstrap login P95 was 561.34 ms and was reported separately; "
            "it was excluded from the authenticated API P95 gate by design.",
            "- The authenticated-only result passed its stated performance "
            "threshold, but does not independently establish Phase 1 freeze approval.",
            "- The documentation reports an inconsistency between the original "
            "JSON threshold metadata and console/raw metric values. The documented "
            "console outcome is retained; JSON threshold flags are not treated "
            "as authoritative.",
            "- These are local synthetic measurements, not production capacity estimates.",
            f"- Source: `{day5_doc.relative_to(root)}`.",
        ])
    else:
        lines.append("- Unavailable: benchmark documentation not found.")
    lines.append("")

    # Early security regression coverage: tests are not historical attack reports.
    lines.extend([
        "### Days 2, 8, 9 and 10 — Authentication, BOLA and API exposure coverage",
        "",
    ])

    early_tests = {
        2: "tests/test_day2_auth_bola.py",
        8: "tests/test_day8_bola_attack.py",
        9: "tests/test_day9_privesc_attack.py",
        10: "tests/test_day10_shadow_zombie.py",
    }

    early_descriptions = {
        2: (
            "Authentication and authorization regression tests, including token "
            "validation, own-resource access, cross-user order controls, and "
            "intentional billing BOLA and legacy-route cases."
        ),
        8: (
            "BOLA attack-harness classification, targeted invoice checks, "
            "cross-user findings, own-invoice controls, and local-target validation."
        ),
        9: (
            "Privilege-escalation harness classification, collection checks, "
            "an eight-case test matrix, and intentional billing escalation behavior."
        ),
        10: (
            "Shadow and zombie endpoint behavior, unauthenticated or weakly "
            "authenticated legacy routes, and controls protecting v2 endpoints."
        ),
    }

    for day, relative in early_tests.items():
        path = root / relative
        if path.is_file():
            lines.append(f"- **Day {day}:** {early_descriptions[day]}")
            lines.append(f"  - Test source: `{relative}`.")
        else:
            lines.append(f"- **Day {day}:** Test source unavailable (`{relative}`).")

    lines.extend([
        "- These files establish the presence of regression tests and attack-harness "
        "logic. They do not establish that a historical attack campaign was executed "
        "or provide an archived runtime finding count.",
        "- The intentionally vulnerable billing and legacy endpoints are lab "
        "fixtures; they must not be interpreted as acceptable production behavior.",
        "",
    ])

    # Day 12: reconstructed ground-truth manifest.
    manifest = docs / "shadow_zombie_manifest.md"
    lines.extend([
        "### Day 12 — Shadow and zombie API ground truth",
        "",
    ])
    if manifest.is_file():
        lines.append(
            "- The available manifest documents seven representative endpoints. "
            "It is explicitly reconstructed from tests, service code, and the "
            "discovery baseline; it is not the recovered original manifest."
        )
        lines.append(
            "- Ground-truth matching requires service, HTTP method, and normalized "
            "path. The manifest is not independent proof that every endpoint was "
            "discovered."
        )
        lines.append(f"- Source: `{manifest.relative_to(root)}`.")
    else:
        lines.append("- Unavailable: manifest file not found.")
    lines.append("")

    # Day 15: documentation-only benchmark evidence.
    lines.extend([
        "### Day 15 — Latency overhead",
        "",
    ])
    day15_doc = docs / "day15-milestone-latency.md"
    if day15_doc.is_file():
        lines.extend([
            "- Available results are documented rather than backed by a discovered "
            "machine-readable Day 15 JSON report.",
            "- Baseline P95: **85.77 ms**; mock-sidecar P95: **122.43 ms**.",
            "- Observed P95 delta: **36.66 ms**. The strict overhead target of less "
            "than 5 ms was not met.",
            "- The benchmark used a mock proxy/sidecar, not real eBPF enforcement.",
            "- Status: pipeline validated, pending real-hardware validation.",
            f"- Source: `{day15_doc.relative_to(root)}`.",
        ])
    else:
        lines.append("- Unavailable: Day 15 benchmark documentation not found.")
    lines.append("")

    # Day 16: latest valid real-time flagging report.
    lines.extend(["### Day 16 — Real-time detection", ""])
    day16_path = latest_json(logs, "realtime_flagging_*/realtime_flagging_report.json")
    day16 = None
    day16_status = "no matching report"
    if day16_path:
        day16, day16_status = load_json(day16_path)

    if day16:
        owners = day16.get("distinct_cross_user_owners")
        owner_count = len(owners) if isinstance(owners, list) else None
        lines.extend([
            f"- Selected latest report: `{day16_path.relative_to(root)}`.",
            f"- Status: **{day16.get('status', 'Unavailable')}**.",
            f"- Attack records: {display(day16.get('attack_record_count'))}; "
            f"cross-user records: {display(day16.get('cross_user_record_count'))}.",
            f"- Distinct cross-user owners: {display(owner_count)}; "
            f"detection latency: {display(day16.get('detection_latency_seconds'), ' s')}.",
            f"- Failure list: `{day16.get('failures', 'Unavailable')}`.",
            "- This is a selected local run, not proof of production-wide detection.",
        ])
    else:
        lines.append(f"- Unavailable: {day16_status}.")
    lines.append("")

    # Day 18: prefer the explicit rerun report.
    day18_relative = (
        "logs/day18_20261031_120756/rate_limit_effectiveness_report_rerun.json"
    )
    day18, day18_status = read(day18_relative)
    lines.extend(["### Day 18 — Rate-limit effectiveness", ""])
    if day18:
        runs = day18.get("runs", {})
        checks = day18.get("checks", {})
        flood = runs.get("flood", {}) if isinstance(runs, dict) else {}
        legitimate = runs.get("legitimate", {}) if isinstance(runs, dict) else {}
        credential = runs.get("credential_stuffing", {}) if isinstance(runs, dict) else {}
        lines.extend([
            f"- Rerun overall status: **{day18.get('overall', 'Unavailable')}**.",
            f"- Flood blocked rate: {display(flood.get('blocked_rate') * 100 if isinstance(flood.get('blocked_rate'), (int, float)) else None, '%')}.",
            f"- Legitimate success rate: {display(legitimate.get('success_rate') * 100 if isinstance(legitimate.get('success_rate'), (int, float)) else None, '%')}.",
            f"- Credential-stuffing blocked rate: {display(credential.get('blocked_rate') * 100 if isinstance(credential.get('blocked_rate'), (int, float)) else None, '%')}.",
            f"- Flood check: `{checks.get('flood_blocking', {}).get('pass', 'Unavailable')}`; "
            f"legitimate-success check: `{checks.get('legitimate_success', {}).get('pass', 'Unavailable')}`.",
            "- The initial report failed the legitimate-success threshold; the rerun "
            "passed using a separate legitimate-traffic sample.",
            "- Scope: temporary local mock limiter; not production validation.",
            f"- Source: `{day18_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day18_status}.")
    lines.append("")

    # Day 19: controlled kernel packet-drop observation.
    day19_relative = "logs/day19_kernel_drop_report.json"
    day19, day19_status = read(day19_relative)
    lines.extend(["### Day 19 — Kernel packet-drop observation", ""])
    if day19:
        steps = day19.get("steps", {})
        map_dump = steps.get("map_dump", {}) if isinstance(steps, dict) else {}
        counters = (
            map_dump.get("counters", {})
            if isinstance(map_dump, dict)
            else {}
        )
        if not isinstance(counters, dict):
            counters = {}

        cleanup = day19.get("cleanup", {})
        if not isinstance(cleanup, dict):
            cleanup = {}
        lines.extend([
            f"- Overall observation: **{day19.get('overall', 'Unavailable')}**.",
            f"- Interface: `{day19.get('interface', 'Unavailable')}`; "
            f"destination port: `{day19.get('destination_port', 'Unavailable')}`.",
            f"- Map counters: matched `{counters.get('matched', 'Unavailable')}`, "
            f"dropped `{counters.get('dropped', 'Unavailable')}`.",
            f"- Cleanup complete: `{cleanup.get('complete', 'Unavailable')}`.",
            "- This is a controlled loopback packet-counter observation. Packet "
            "counters and a client timeout do not independently prove that an "
            "HTTP request was blocked before application processing.",
            f"- Source: `{day19_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day19_status}.")
    lines.append("")

    # Day 20: fail-open simulation.
    day20_path = latest_json(logs, "fail_open_report_*.json")
    day20, day20_status = load_json(day20_path) if day20_path else (None, "missing")
    lines.extend(["### Day 20 — Fail-open behavior", ""])
    if day20:
        lines.extend([
            f"- Report source: `{day20_path.relative_to(root)}`.",
            f"- Report status: **{day20.get('overall', day20.get('status', 'See source report'))}**.",
            "- Evidence is an application-layer HTTP simulation, not proof of real "
            "TC/eBPF daemon-failure behavior.",
        ])
    else:
        lines.append(f"- Unavailable: {day20_status}.")
    lines.append("")

    # Day 21: zero-drop simulation.
    day21_relative = "logs/zero_drop_report.json"
    day21, day21_status = read(day21_relative)
    lines.extend(["### Day 21 — Legitimate-traffic zero-drop simulation", ""])
    if day21:
        adapter = day21.get("adapter_stats", {})
        if not isinstance(adapter, dict):
            adapter = {}

        legitimate_requests = day21.get(
            "legitimate_request_count",
            adapter.get("legitimate_requests", "Unavailable"),
        )
        legitimate_success = day21.get(
            "legitimate_success_count",
            "Unavailable",
        )

        lines.extend([
            f"- Overall status: **{day21.get('overall', 'Unavailable')}**.",
            f"- Evidence type: `{day21.get('evidence_type', adapter.get('evidence_type', 'Unavailable'))}`.",
            f"- Kernel-drop proof: `{day21.get('kernel_drop_proof', adapter.get('kernel_drop_proof', 'Unavailable'))}`.",
            f"- Legitimate requests: `{legitimate_requests}`; "
            f"successful: `{legitimate_success}`.",
            "- This report identifies application-layer simulation evidence, not "
            "kernel packet-drop proof.",
            f"- Source: `{day21_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day21_status}.")
    lines.append("")

    # Day 22: mixed traffic.
    day22_relative = "logs/mixed_stress_report.json"
    day22, day22_status = read(day22_relative)
    lines.extend(["### Day 22 — Mixed legitimate and adversarial traffic", ""])
    if day22:
        stats = day22.get("adapter_stats", {})
        if not isinstance(stats, dict):
            stats = {}
        lines.extend([
            f"- Overall status: **{day22.get('overall', 'Unavailable')}**.",
            f"- Evidence type: `{stats.get('evidence_type', day22.get('evidence_type', 'Unavailable'))}`.",
            f"- Legitimate requests: {display(stats.get('legitimate_requests'))}; "
            f"adversarial requests: {display(stats.get('attack_requests'))}.",
            f"- Adversarial requests blocked: {display(stats.get('attack_blocked'))}.",
            f"- Kernel-drop proof: `{stats.get('kernel_drop_proof', day22.get('kernel_drop_proof', 'Unavailable'))}`.",
            "- The 90/10 mixed-traffic result is application-layer simulation "
            "evidence and must not be described as kernel enforcement.",
            f"- Source: `{day22_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day22_status}.")
    lines.append("")

    # Day 23: strongest kernel-drop evidence.
    day23_relative = "logs/day23_kernel_blocking_at_scale_report.json"
    day23, day23_status = read(day23_relative)
    lines.extend(["### Day 23 — Kernel blocking at scale", ""])
    if day23:
        counters = day23.get("kernel_counters", {})
        workload = day23.get("workload", {})
        cleanup = day23.get("cleanup", {})
        if not isinstance(counters, dict):
            counters = {}
        if not isinstance(workload, dict):
            workload = {}
        if not isinstance(cleanup, dict):
            cleanup = {}
        lines.extend([
            f"- Overall status: **{day23.get('overall', 'Unavailable')}**.",
            f"- Evidence type: `{day23.get('evidence_type', 'Unavailable')}`; "
            f"kernel-drop proof: `{day23.get('kernel_drop_proof', 'Unavailable')}`.",
            f"- Concurrency evidence: `{day23.get('concurrency_evidence', 'Unavailable')}`.",
            f"- Attempts completed: `{workload.get('attempts_completed', 'Unavailable')}`; "
            f"matched packets: `{counters.get('matched', 'Unavailable')}`; "
            f"dropped packets: `{counters.get('dropped', 'Unavailable')}`.",
            f"- Cleanup complete: `{cleanup.get('complete', 'Unavailable')}`.",
            "- This is controlled loopback kernel-drop evidence. It is stronger "
            "than the application-layer simulations, but is not production network "
            "certification.",
            f"- Source: `{day23_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day23_status}.")
    lines.append("")

    # Day 23 certification evaluation.
    cert_relative = "logs/day23_kernel_certification_report.json"
    cert, cert_status = read(cert_relative)
    if cert:
        lines.extend([
            "#### Day 23 certification evaluator",
            "",
            f"- Kernel certification: **{cert.get('kernel_certification', 'Unavailable')}**.",
            f"- Concurrency status: **{cert.get('concurrency_status', 'Unavailable')}**.",
            f"- Overall evaluator status: **{cert.get('overall', 'Unavailable')}**.",
            f"- Source: `{cert_relative}`.",
            "",
        ])
    else:
        lines.extend([f"- Certification evaluator unavailable: {cert_status}.", ""])

        # Phase freeze evaluation.
    freeze_relative = "logs/phase3_freeze_report.json"
    freeze, freeze_status = read(freeze_relative)
    lines.extend(["### Phase 1–3 — Freeze and certification status", ""])

    if freeze:
        lines.extend([
            f"- Phase 3 overall freeze status: "
            f"**{freeze.get('phase3_freeze_status', 'Unavailable')}**.",
            f"- Kernel certification status: "
            f"**{freeze.get('kernel_certification', 'Unavailable')}**.",
        ])

        checks = freeze.get("checks", {})
        if not isinstance(checks, dict):
            checks = {}

        phase1 = checks.get("phase1", {})
        if isinstance(phase1, dict):
            lines.append(
                f"- Phase 1: **{phase1.get('status', 'Unavailable')}**; "
                f"{phase1.get('check_count', 'Unavailable')} historical checks "
                f"reported. The referenced archive "
                f"`{phase1.get('source', 'Unavailable')}` was not present in "
                "the inspected checkout; this is not a fresh Phase 1 validation."
            )

        phase2 = checks.get("phase2", {})
        if isinstance(phase2, dict):
            reported = phase2.get("reported_checks", {})
            if not isinstance(reported, dict):
                reported = {}
            lines.append(
                f"- Phase 2: **{phase2.get('status', 'Unavailable')}**; "
                f"{reported.get('passed', 'Unavailable')}/"
                f"{reported.get('total', 'Unavailable')} checks are documented "
                "as passing. The referenced freeze document and machine-readable "
                "report were not present in the inspected checkout; this result "
                "cannot be independently verified here."
            )

        day15_freeze = checks.get("day15", {})
        if isinstance(day15_freeze, dict):
            lines.append(
                f"- Day 15 freeze check: **{day15_freeze.get('status', 'Unavailable')}**; "
                f"recorded overhead deltas: "
                f"`{day15_freeze.get('measured_deltas_ms', 'Unavailable')}` ms "
                "against a strict less-than-5-ms target."
            )

        for day in (18, 19, 20, 21, 22, 23):
            item = checks.get(f"day{day}", {})
            if isinstance(item, dict):
                lines.append(
                    f"- Day {day} freeze evaluation: "
                    f"**{item.get('status', 'Unavailable')}**."
                )

        limitations = freeze.get("limitations", [])
        if isinstance(limitations, list) and limitations:
            lines.append("- Recorded freeze limitations:")
            for limitation in limitations:
                lines.append(f"  - {limitation}")

        lines.append(f"- Source: `{freeze_relative}`.")
    else:
        lines.append(f"- Freeze evaluation unavailable: {freeze_status}.")

    lines.append("")

    # Day 25: PII scan.
    day25_relative = "logs/pii_leakage_report.json"
    day25, day25_status = read(day25_relative)
    lines.extend(["### Day 25 — PII exposure scan", ""])
    if day25:
        lines.extend([
            f"- Status: **{day25.get('status', 'Unavailable')}**.",
            f"- Findings: **{display(day25.get('finding_count'))}**; "
            f"fixture payloads: {display(day25.get('fixture_payload_count'))}.",
            f"- Scope: `{day25.get('audit_scope', 'Unavailable')}`.",
            "- Findings represent matches in the inspected API response bodies, "
            "selected SQLite fields, and selected service-log lines. This is not "
            "a full disk, packet-capture, or universal PII scan.",
            f"- Source: `{day25_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day25_status}.")
    lines.append("")

    # Day 26: OWASP regression.
    day26_relative = "logs/owasp_regression_report.json"
    day26, day26_status = read(day26_relative)
    lines.extend(["### Day 26 — OWASP API Security Top 10 regression", ""])
    if day26:
        coverage = day26.get("coverage", {})
        if not isinstance(coverage, dict):
            coverage = {}
        lines.extend([
            f"- Overall status: **{day26.get('overall', 'Unavailable')}**.",
            f"- Coverage percentage: **{display(coverage.get('percentage'), '%')}**.",
            f"- Covered: {display(coverage.get('covered'))}; "
            f"partial: {display(coverage.get('partial'))}; "
            f"failed: {display(coverage.get('failed'))}; "
            f"not run: {display(coverage.get('not_run'))}.",
            "- The score is lab-specific regression coverage, not OWASP "
            "certification. Historical evidence, skipped tests, and out-of-scope "
            "categories are not equivalent to passing security tests.",
            f"- Source: `{day26_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day26_status}.")
    lines.append("")

    # Day 27: endurance run.
    day27_path = latest_json(logs / "day27", "*/endurance_report.json")
    day27, day27_status = (
        load_json(day27_path) if day27_path else (None, "no matching report")
    )
    day27_relative = (
        str(day27_path.relative_to(root)) if day27_path else "logs/day27"
    )
    lines.extend(["### Day 27 — Endurance testing", ""])
    if day27:
        lines.extend([
            f"- Status: **{day27.get('status', 'Unavailable')}**.",
            f"- Evidence type: `{day27.get('evidence_type', 'Unavailable')}`.",
            f"- Target duration: {display(day27.get('target_duration_seconds'), ' s')}; "
            f"observed duration: {display(day27.get('observed_duration_seconds'), ' s')}.",
            f"- Checkpoints: {display(day27.get('checkpoint_count'))}; "
            f"samples: {display(day27.get('sample_count'))}; "
            f"sampling errors: {display(day27.get('sampling_error_count'))}.",
            f"- Interrupted: `{day27.get('interrupted', 'Unavailable')}`.",
            (
               "- The run was interrupted before reaching its six-hour target. "
               "It is not a completed six-hour endurance certification."
               if day27.get("status") == "INTERRUPTED"
               else (
                  "- The six-hour endurance target was completed."
                  if day27.get("status") == "COMPLETED"
                  and day27.get("observed_duration_seconds", 0) >= 21600
                  else "- The available run does not establish completion of the six-hour endurance target."
                  )
            ),
            f"- Source: `{day27_relative}`.",
        ])
    else:
        lines.append(f"- Unavailable: {day27_status}.")
    lines.append("")

    # Availability ledger for all days.
    known = {
        1: "No authoritative report identified in this compilation",
        2: "Authentication/BOLA regression test source; no historical run report identified",
        3: "No authoritative report identified in this compilation",
        4: "No authoritative report identified in this compilation",
        5: "Documented baseline and authenticated benchmark results; raw result files unavailable",
        6: "No authoritative report identified in this compilation",
        7: "No authoritative report identified in this compilation",
        8: "BOLA attack-harness regression tests; no historical run report identified",
        9: "Privilege-escalation harness regression tests; no historical run report identified",
        10: "Shadow/zombie API regression tests; no historical run report identified",
        11: "No authoritative report identified in this compilation",
        12: "Reconstructed shadow/zombie manifest",
        13: "No authoritative report identified in this compilation",
        14: "No authoritative report identified in this compilation",
        15: "Documentation-only benchmark evidence",
        16: "Real-time flagging reports",
        17: "No authoritative report identified in this compilation",
        18: "Rate-limit effectiveness rerun",
        19: "Controlled kernel packet-drop observation",
        20: "Fail-open application-layer simulation",
        21: "Zero-drop application-layer simulation",
        22: "Mixed-traffic application-layer simulation",
        23: "Kernel-drop-at-scale and certification reports",
        24: "No authoritative report identified in this compilation",
        25: "PII exposure scan",
        26: "OWASP regression report",
        27: "Interrupted endurance run",
    }
    lines.extend([
        "## 3. Evidence availability by day",
        "",
        "| Day | Evidence currently identified |",
        "|---:|---|",
    ])
    for day in range(1, 28):
        label = known.get(day, "No authoritative report identified in this compilation")
        lines.append(f"| {day} | {label} |")
    lines.append("")

    append_artifact_inventory(lines, root)
    append_latency_graphs(lines)

    lines.extend([
        "## 4. Overall interpretation",
        "",
        "The available evidence demonstrates several independently exercised "
        "capabilities in a controlled local lab. It includes application-layer "
        "rate-limit and traffic simulations, a reconstructed API ground-truth "
        "manifest, PII scanning, OWASP regression coverage, and controlled "
        "loopback kernel packet-drop experiments.",
        "",
        "These evidence classes are not interchangeable. In particular, the "
        "Day 20–22 simulations do not prove kernel packet drops. Day 23 provides "
        "the strongest kernel-drop evidence in the available reports, but its "
        "controlled loopback setup does not establish production network "
        "reliability. Day 27 results should be interpreted using the recorded status, duration, and sampling evidence.",
        "",
        "## 5. Missing evidence and limitations",
        "",
        "Days without an identified source are marked as unavailable in the "
        "evidence table. This means the compiler did not identify an authoritative "
        "source in the reviewed evidence set; it does not prove that no such "
        "evidence exists elsewhere in the repository.",
        "",
        "The expected `docs/vulnerabilities.md` register was not present in "
        "the inspected repository. This report therefore does not claim to provide "
        "a complete vulnerability register or invent vulnerability identifiers.",
        "",
        "This report is a compilation of supplied local evidence. It is not a "
        "production penetration test, independent audit, or certification.",
        "",
        "## 6. Recommendations and next steps",
        "",
        "1. Investigate the Day 5 login latency hotspot without weakening the "
        "documented performance thresholds.",
        "2. Re-run the Day 15 monitoring-overhead comparison with real eBPF "
        "enforcement on representative hardware; retain the strict less-than-5-ms "
        "acceptance target.",
        "3. Recover or regenerate the missing Phase 1 and Phase 2 freeze archives "
        "through their approved validation workflows before claiming independently "
        "verified phase sign-off.",
        "4. Extend Day 23 kernel-drop validation beyond controlled loopback testing "
        "before making production-network reliability claims.",
        "5. Preserve Day 27 endurance reports, checkpoints, and sampling evidence; distinguish completed runs from interrupted or partial runs.",
        "6. Address the partial Day 26 OWASP coverage, including categories marked "
        "partial or not run, and preserve explicit out-of-scope justifications.",
        "7. Investigate and remediate the intentionally vulnerable BOLA, shadow, "
        "and zombie lab endpoints before any production deployment.",
        "8. Preserve raw benchmark JSON and console logs together, and reconcile "
        "inconsistent threshold metadata before automated acceptance decisions.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="appsec-testing project root (defaults to the detected project root)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output Markdown path (defaults to docs/Performance_Security_Validation_Report.md)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output or (
        root / "docs" / "Performance_Security_Validation_Report.md"
    )
    if not output.is_absolute():
        output = root / output

    try:
        report = build_report(root)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    except OSError as exc:
        parser.error(f"could not write report: {exc}")

    print(f"Report written: {output}")
    print(f"Project root: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
