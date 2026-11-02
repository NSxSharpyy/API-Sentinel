#!/usr/bin/env python3
"""Day 26: OWASP API Security Top 10 (2023) regression suite."""

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


APPSEC_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = APPSEC_ROOT / "tests"
LOG_ROOT = APPSEC_ROOT / "logs"
REPORT_PATH = LOG_ROOT / "owasp_regression_report.json"

TEST_MODULES = [
    "tests/test_day2_auth_bola.py",
    "tests/test_day8_bola_attack.py",
    "tests/test_day10_shadow_zombie.py",
    "tests/test_day11_endpoint_scanner.py",
    "tests/test_day12_discovery_verification.py",
    "tests/test_day17_bot_traffic.py",
    "tests/test_day18_rate_limiting.py",
    "tests/test_day24_pii_payloads.py",
    "tests/test_day25_pii_leakage.py",
]

DESELECTED_TESTS = [
    "tests/test_day24_pii_payloads.py::test_cli_run_produces_expected_output_file",
]

EVIDENCE_PATHS = {
    "day12_discovery": LOG_ROOT / "discovery_verification_report.json",
    "day18_rate_limit": (
        LOG_ROOT / "day18_20261031_120756"
        / "rate_limit_effectiveness_report_rerun.json"
    ),
    "day25_pii": LOG_ROOT / "pii_leakage_report.json",
}

CATEGORY_DEFINITIONS = [
    {
        "id": "API1",
        "name": "Broken Object Level Authorization",
        "status": "COVERED",
        "modules": [
            "test_day2_auth_bola.py",
            "test_day8_bola_attack.py",
            "test_day10_shadow_zombie.py",
        ],
        "limitations": [
            "Coverage is limited to the implemented local lab endpoints.",
            "Day 8 scanner tests use mocked responses and do not prove live production behavior.",
        ],
    },
    {
        "id": "API2",
        "name": "Broken Authentication",
        "status": "PARTIAL",
        "modules": [
            "test_day2_auth_bola.py",
            "test_day10_shadow_zombie.py",
            "test_day17_bot_traffic.py",
        ],
        "limitations": [
            "Authentication regression tests cover selected token and legacy authentication behavior.",
            "Historical credential-stuffing outcomes do not establish comprehensive authentication security.",
        ],
    },
    {
        "id": "API3",
        "name": "Broken Object Property Level Authorization",
        "status": "PARTIAL",
        "modules": ["test_day25_pii_leakage.py"],
        "evidence": ["day25_pii"],
        "limitations": [
            "Day 25 verifies selected plaintext PII exposure paths.",
            "This is not comprehensive property-level authorization testing.",
        ],
    },
    {
        "id": "API4",
        "name": "Unrestricted Resource Consumption",
        "status": "PARTIAL",
        "modules": [
            "test_day17_bot_traffic.py",
            "test_day18_rate_limiting.py",
        ],
        "evidence": ["day18_rate_limit"],
        "limitations": [
            "Rate-limiter evidence is a local integration test using a temporary mock limiter.",
            "It does not establish production capacity or protection against every resource-exhaustion vector.",
        ],
    },
    {
        "id": "API5",
        "name": "Broken Function Level Authorization",
        "status": "COVERED",
        "modules": ["test_day10_shadow_zombie.py"],
        "limitations": [
            "Coverage concerns the administrative and legacy routes implemented in this lab.",
        ],
    },
    {
        "id": "API6",
        "name": "Unrestricted Access to Sensitive Business Flows",
        "status": "OUT_OF_SCOPE",
        "modules": [],
        "limitations": [
            "The inspected lab does not expose a qualifying sensitive business workflow such as purchasing or payment transfer.",
            "Out of scope does not mean the category is secure.",
        ],
    },
    {
        "id": "API7",
        "name": "Server Side Request Forgery",
        "status": "OUT_OF_SCOPE",
        "modules": [],
        "limitations": [
            "No outbound URL-fetching functionality was identified in the inspected services.",
            "No SSRF security conclusion is made.",
        ],
    },
    {
        "id": "API8",
        "name": "Security Misconfiguration",
        "status": "NOT_RUN",
        "modules": [],
        "limitations": [
            "No sufficient dedicated security-misconfiguration validation evidence was identified.",
            "Source-level debug settings alone are not a complete configuration assessment.",
        ],
    },
    {
        "id": "API9",
        "name": "Improper Inventory Management",
        "status": "PARTIAL",
        "modules": [
            "test_day11_endpoint_scanner.py",
            "test_day12_discovery_verification.py",
        ],
        "evidence": ["day12_discovery"],
        "limitations": [
            "Historical Day 12 verification failed: 6 of 7 ground-truth endpoints matched.",
            "Historical precision and recall were both approximately 85.7%.",
            "Historical mock verification is not a fresh live inventory scan.",
        ],
    },
    {
        "id": "API10",
        "name": "Unsafe Consumption of APIs",
        "status": "OUT_OF_SCOPE",
        "modules": [],
        "limitations": [
            "No third-party API consumption functionality was identified in the inspected lab services.",
            "Out of scope does not establish safe third-party API consumption.",
        ],
    },
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_report(report, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def load_historical_evidence():
    evidence = {}

    for name, path in EVIDENCE_PATHS.items():
        try:
            display_path = str(path.relative_to(APPSEC_ROOT))
        except ValueError:
            display_path = str(path)

        item = {
            "available": path.is_file(),
            "path": display_path,
        }

        if not path.is_file():
            item["status"] = "MISSING"
            evidence[name] = item
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            item["status"] = "READABLE"
            item["generated_at"] = (
                data.get("generated_at")
                or data.get("completed_at")
            )

            if name == "day12_discovery":
                item["verdict"] = data.get("verdict")
                item["matched_endpoints"] = data.get("matched_endpoints")
                item["ground_truth_endpoints"] = data.get(
                    "ground_truth_endpoints"
                )
                item["precision"] = data.get("precision")
                item["recall"] = data.get("recall")

            elif name == "day18_rate_limit":
                item["overall"] = data.get("overall")
                item["validation_class"] = data.get("validation_class")
                item["scope"] = data.get("scope")

            elif name == "day25_pii":
                item["day"] = data.get("day")
                item["status_value"] = data.get("status")
                item["finding_count"] = data.get("finding_count")
                item["cleanup_complete"] = data.get(
                    "cleanup", {}
                ).get("complete")

        except (OSError, json.JSONDecodeError) as exc:
            item["status"] = "UNREADABLE"
            item["error_type"] = type(exc).__name__

        evidence[name] = item

    return evidence


def parse_junit(path):
    results = {}

    root = ET.parse(path).getroot()

    for case in root.iter("testcase"):
        classname = case.attrib.get("classname", "")
        module = classname.rsplit(".", 1)[-1] + ".py"

        result = results.setdefault(
            module,
            {"passed": 0, "failed": 0, "errors": 0, "skipped": 0},
        )

        if case.find("failure") is not None:
            result["failed"] += 1
        elif case.find("error") is not None:
            result["errors"] += 1
        elif case.find("skipped") is not None:
            result["skipped"] += 1
        else:
            result["passed"] += 1

    return results


def run_regression_tests(timeout):
    with tempfile.TemporaryDirectory(prefix="api_sentinel_day26_") as temp:
        junit_path = Path(temp) / "regression.xml"

        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *TEST_MODULES,
            *(f"--deselect={test}" for test in DESELECTED_TESTS),
            f"--junitxml={junit_path}",
        ]

        try:
            result = subprocess.run(
                command,
                cwd=APPSEC_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "execution_status": "TIMEOUT",
                "exit_code": None,
                "modules": {},
                "summary": {},
                "stdout": "",
                "stderr": "",
            }

        if not junit_path.is_file():
            return {
                "execution_status": "NO_JUNIT_REPORT",
                "exit_code": result.returncode,
                "modules": {},
                "summary": {},
                "stdout": result.stdout[-12000:],
                "stderr": result.stderr[-12000:],
            }

        try:
            modules = parse_junit(junit_path)
        except (ET.ParseError, OSError):
            modules = {}

        summary = {
            key: sum(item[key] for item in modules.values())
            for key in ("passed", "failed", "errors", "skipped")
        }

        summary["deselected"] = len(DESELECTED_TESTS)

        return {
            "execution_status": (
                "COMPLETED" if result.returncode == 0 else "FAILED"
            ),
            "exit_code": result.returncode,
            "modules": modules,
            "summary": summary,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
        }


def evaluate_categories(test_results, historical):
    module_results = test_results["modules"]
    categories = []

    for definition in CATEGORY_DEFINITIONS:
        item = {
            "id": definition["id"],
            "name": definition["name"],
            "status": definition["status"],
            "test_modules": {},
            "test_execution_status": "NOT_RUN",
            "historical_evidence": {},
            "limitations": list(definition["limitations"]),
        }

        required_evidence = definition.get("evidence", [])
        for evidence_name in required_evidence:
            item["historical_evidence"][evidence_name] = (
                historical.get(evidence_name, {})
            )

        for module in definition["modules"]:
            result = module_results.get(module)
            item["test_modules"][module] = (
                result if result is not None else {"status": "NOT_COLLECTED"}
            )

        if definition["status"] in ("COVERED", "PARTIAL"):
            selected = [
                module_results[module]
                for module in definition["modules"]
                if module in module_results
            ]

            if not selected:
                item["status"] = "BLOCKED"
                item["test_execution_status"] = "NOT_COLLECTED"
            else:
                passed = sum(result["passed"] for result in selected)
                failed = sum(result["failed"] for result in selected)
                errors = sum(result["errors"] for result in selected)
                skipped = sum(result["skipped"] for result in selected)

                item["test_execution_status"] = (
                    "FAILED" if failed or errors
                    else "NOT_RUN" if not passed and skipped
                    else "PASS_WITH_SKIPS" if skipped
                    else "PASS"
                )

                if failed or errors:
                    item["status"] = "FAILED"
                elif not passed:
                    item["status"] = "NOT_RUN"

            missing_evidence = [
                name for name in required_evidence
                if historical.get(name, {}).get("status") != "READABLE"
            ]
            if missing_evidence and item["status"] != "FAILED":
                item["status"] = "BLOCKED"
                item["limitations"].append(
                    "Required historical evidence is missing or unreadable: "
                    + ", ".join(missing_evidence)
                )

        categories.append(item)

    return categories


def calculate_coverage(categories):
    in_scope = [
        item for item in categories
        if item["status"] != "OUT_OF_SCOPE"
    ]

    weights = {
        "COVERED": 1.0,
        "PARTIAL": 0.5,
        "FAILED": 0.0,
        "BLOCKED": 0.0,
        "NOT_RUN": 0.0,
    }

    earned = sum(weights.get(item["status"], 0.0) for item in in_scope)
    possible = len(in_scope)

    return {
        "method": (
            "COVERED=1, PARTIAL=0.5, FAILED/BLOCKED/NOT_RUN=0; "
            "OUT_OF_SCOPE excluded from denominator"
        ),
        "in_scope_categories": possible,
        "out_of_scope_categories": len(categories) - possible,
        "covered": sum(item["status"] == "COVERED" for item in in_scope),
        "partial": sum(item["status"] == "PARTIAL" for item in in_scope),
        "failed": sum(item["status"] == "FAILED" for item in in_scope),
        "blocked": sum(item["status"] == "BLOCKED" for item in in_scope),
        "not_run": sum(item["status"] == "NOT_RUN" for item in in_scope),
        "weighted_score": round(earned, 2),
        "maximum_score": possible,
        "percentage": round(earned / possible * 100, 2) if possible else 0.0,
    }


def build_report(timeout):
    started = utc_now()
    tests = run_regression_tests(timeout)
    historical = load_historical_evidence()
    categories = evaluate_categories(tests, historical)
    coverage = calculate_coverage(categories)

    test_summary = tests["summary"]
    execution_ok = tests["execution_status"] == "COMPLETED"
    no_test_failures = (
        test_summary.get("failed", 0) == 0
        and test_summary.get("errors", 0) == 0
    )

    if not execution_ok or not no_test_failures:
        overall = "FAIL"
    elif all(item["status"] == "COVERED" for item in categories):
        overall = "PASS"
    else:
        overall = "PARTIAL"

    return {
        "schema_version": 1,
        "day": 26,
        "title": "OWASP API Security Top 10 (2023) Regression",
        "started_at": started,
        "completed_at": utc_now(),
        "scope": "Authorized local API-Sentinel lab",
        "taxonomy": "OWASP API Security Top 10 (2023)",
        "overall": overall,
        "execution": {
            "status": tests["execution_status"],
            "exit_code": tests["exit_code"],
            "command_modules": TEST_MODULES,
            "deselected_tests": DESELECTED_TESTS,
            "summary": test_summary,
            "module_results": tests["modules"],
            "stdout_tail": tests["stdout"],
            "stderr_tail": tests["stderr"],
        },
        "historical_evidence": historical,
        "categories": categories,
        "coverage": coverage,
        "limitations": [
            "Historical reports are evidence inputs, not fresh test executions.",
            "Skipped tests are not counted as passed.",
            "Out-of-scope categories are excluded from the coverage denominator.",
            "The coverage score is a transparent lab-specific metric, not an OWASP certification.",
            "The suite does not establish production security.",
            "The Day 24 CLI file-overwriting test is deliberately deselected.",
        ],
    }



LIVE_REPORT_PATH = LOG_ROOT / "owasp_regression_live_report.json"
LIVE_SERVICES = {
    "auth": 5001,
    "user": 5002,
    "order": 5003,
    "billing": 5004,
}


def display_evidence_path(path):
    path = Path(path)
    try:
        return str(path.relative_to(APPSEC_ROOT))
    except ValueError:
        return str(path)


def create_live_evidence_dir():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = LOG_ROOT / f"day26_live_{stamp}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = LOG_ROOT / f"{base.name}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def check_live_health(timeout=3):
    import urllib.error
    import urllib.request

    results = {}
    for service, port in LIVE_SERVICES.items():
        url = f"http://127.0.0.1:{port}/health"
        item = {"url": url, "healthy": False}
        try:
            request = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                item["http_status"] = response.status
                payload = json.loads(response.read().decode("utf-8"))
                item["response"] = payload
                item["healthy"] = (
                    response.status == 200
                    and isinstance(payload, dict)
                    and payload.get("status") == "ok"
                )
                if not item["healthy"]:
                    item["reason"] = "Health response did not confirm status=ok"
        except Exception as exc:
            item["error_type"] = type(exc).__name__
        results[service] = item

    return {
        "status": (
            "PASS" if all(item["healthy"] for item in results.values())
            else "BLOCKED"
        ),
        "services": results,
    }


def run_live_command(name, command, evidence_dir, timeout):
    try:
        result = subprocess.run(
            command,
            cwd=APPSEC_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "name": name,
            "status": "COMPLETED" if result.returncode == 0 else "FAILED",
            "exit_code": result.returncode,
            "command": command,
            "stdout_tail": result.stdout[-6000:],
            "stderr_tail": result.stderr[-6000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "status": "TIMEOUT",
            "exit_code": None,
            "command": command,
        }
    except OSError as exc:
        return {
            "name": name,
            "status": "ERROR",
            "exit_code": None,
            "command": command,
            "error_type": type(exc).__name__,
        }


def read_jsonl_summary(path):
    summary = {
        "available": path.is_file(),
        "records": 0,
        "labels": {},
        "http_statuses": {},
        "errors": 0,
        "cross_user_bola_successes": 0,
    }
    if not path.is_file():
        return summary

    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    summary["errors"] += 1
                    continue

                summary["records"] += 1
                label = item.get("label")
                if isinstance(label, str):
                    summary["labels"][label] = (
                        summary["labels"].get(label, 0) + 1
                    )

                status = item.get(
                    "status_code",
                    item.get("http_status", item.get("status")),
                )
                if status is not None:
                    key = str(status)
                    summary["http_statuses"][key] = (
                        summary["http_statuses"].get(key, 0) + 1
                    )
                if (
                    label == "BOLA_SUCCESS"
                    and item.get("cross_user_access") is True
                ):
                    summary["cross_user_bola_successes"] += 1
    except OSError as exc:
        summary["read_error"] = type(exc).__name__

    return summary


def run_api5_observation(timeout=3):
    import urllib.error
    import urllib.request

    url = "http://127.0.0.1:5004/_admin/reset-cache"
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    result = {
        "url": url,
        "method": "POST",
        "scope": "One request to the local lab-only administrative route",
        "observed": False,
    }
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2048).decode("utf-8", errors="replace")
            result["http_status"] = response.status
            result["response"] = body
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {}
            result["observed"] = (
                response.status == 200
                and isinstance(parsed, dict)
                and parsed.get("status") == "cache reset"
            )
    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        result["response"] = exc.read(2048).decode(
            "utf-8", errors="replace"
        )
    except Exception as exc:
        result["error_type"] = type(exc).__name__

    return result


def run_live_orchestration(timeout):
    evidence_dir = create_live_evidence_dir()
    try:
        evidence_directory = display_evidence_path(evidence_dir)
    except ValueError:
        evidence_directory = str(evidence_dir)

    live = {
        "started_at": utc_now(),
        "status": "BLOCKED",
        "evidence_directory": evidence_directory,
        "scope": "Authorized local API-Sentinel services only",
        "health_preflight": check_live_health(),
        "scans": {},
        "observations": {},
        "limitations": [
            "Live results apply only to this local lab run.",
            "A successful scan execution does not certify the API as secure.",
            "BOLA findings and API5 route behavior are reported as observations.",
            "Day 17 workloads are intentionally bounded and are not capacity tests.",
        ],
    }

    if live["health_preflight"]["status"] != "PASS":
        live["reason"] = (
            "At least one service failed its health check; all live scans "
            "were skipped."
        )
        live["completed_at"] = utc_now()
        return live

    day8_dir = evidence_dir / "day08_bola"
    day17_creds_dir = evidence_dir / "day17_credentials"
    day17_flood_dir = evidence_dir / "day17_login_flood"
    day11_dir = evidence_dir / "day11_inventory"
    day25_dir = evidence_dir / "day25_pii"
    for directory in (
        day8_dir, day17_creds_dir, day17_flood_dir, day11_dir, day25_dir
    ):
        directory.mkdir(parents=True)

    commands = [
        (
            "day08_bola_sweep",
            [
                sys.executable, "scripts/attacks/bola_attack.py",
                "--mode", "sweep",
                "--start-id", "1", "--end-id", "20",
                "--delay", "0.05", "--timeout", "3",
                "--output-dir", str(day8_dir),
            ],
            timeout,
        ),
        (
            "day17_credential_stuffing",
            [
                sys.executable, "scripts/attacks/bot_traffic_generator.py",
                "--mode", "creds_stuff",
                "--concurrency", "2",
                "--attempts-per-worker", "10",
                "--output-dir", str(day17_creds_dir),
            ],
            timeout,
        ),
        (
            "day17_invalid_login_flood",
            [
                sys.executable, "scripts/attacks/bot_traffic_generator.py",
                "--mode", "flood",
                "--target", "login",
                "--concurrency", "2",
                "--duration", "2",
                "--output-dir", str(day17_flood_dir),
            ],
            timeout,
        ),
        (
            "day11_safe_endpoint_inventory",
            [
                sys.executable, "scripts/recon/endpoint_scanner.py",
                "--delay", "0.05",
                "--skip-method-enum",
                "--output-dir", str(day11_dir),
            ],
            timeout,
        ),
    ]

    command_results = {}
    for name, command, command_timeout in commands:
        command_results[name] = run_live_command(
            name, command, evidence_dir, command_timeout
        )

    live["scans"].update(command_results)

    # Parse scan evidence even when a tool exits non-zero, so partial
    # observations are retained and not silently discarded.
    live["observations"]["day08_bola"] = read_jsonl_summary(
        day8_dir / "bola_attack.jsonl"
    )
    bola_labels = live["observations"]["day08_bola"]["labels"]

    live["observations"]["day17_credentials"] = read_jsonl_summary(
        day17_creds_dir / "bot_traffic.jsonl"
    )
    live["observations"]["day17_login_flood"] = read_jsonl_summary(
        day17_flood_dir / "bot_traffic.jsonl"
    )

    day11_report = day11_dir / "discovery_report.json"
    inventory = {
        "available": day11_report.is_file(),
        "path": str(day11_report.relative_to(APPSEC_ROOT))
        if day11_report.is_relative_to(APPSEC_ROOT) else str(day11_report),
    }
    if day11_report.is_file():
        try:
            data = json.loads(day11_report.read_text(encoding="utf-8"))
            classifications = data.get("endpoint_classification", {})
            counts = {}
            for service_data in classifications.values():
                if not isinstance(service_data, dict):
                    continue
                for classification in service_data.values():
                    if isinstance(classification, str):
                        counts[classification] = counts.get(classification, 0) + 1
            inventory["total_discovered"] = data.get("total_discovered")
            inventory["classification_counts"] = counts
            inventory["undocumented_or_legacy_candidates"] = sum(
                count for label, count in counts.items()
                if label != "documented_v2"
            )
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            inventory["read_error"] = type(exc).__name__
    live["observations"]["day11_inventory"] = inventory

    live["observations"]["api5_admin_route"] = run_api5_observation()

    day25_report_path = day25_dir / "pii_leakage_report.json"
    day25_command = [
        sys.executable, "scripts/compliance/pii_leakage_scanner.py",
        "--execute", "--report", str(day25_report_path),
    ]
    live["scans"]["day25_pii_audit"] = run_live_command(
        "day25_pii_audit", day25_command, evidence_dir, timeout
    )

    day25_observation = {
        "report_available": day25_report_path.is_file(),
        "path": display_evidence_path(day25_report_path),
    }
    if day25_report_path.is_file():
        try:
            data = json.loads(day25_report_path.read_text(encoding="utf-8"))
            cleanup = data.get("cleanup", {})
            day25_observation.update({
                "status": data.get("status"),
                "finding_count": data.get("finding_count"),
                "cleanup_attempted": cleanup.get("attempted"),
                "cleanup_complete": cleanup.get("complete"),
            })
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            day25_observation["read_error"] = type(exc).__name__
    live["observations"]["day25_pii"] = day25_observation

    results = list(live["scans"].values())
    any_failed = any(item["status"] != "COMPLETED" for item in results)
    cleanup_incomplete = (
        not day25_observation.get("report_available")
        or day25_observation.get("status") != "COMPLETE"
        or day25_observation.get("cleanup_complete") is not True
    )

    if cleanup_incomplete:
        live["status"] = "FAILED"
        live["reason"] = "Day 25 audit cleanup was not confirmed complete."
    elif any_failed:
        live["status"] = "PARTIAL"
    else:
        live["status"] = "COMPLETED"

    live["completed_at"] = utc_now()
    return live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Maximum pytest/live command execution time in seconds.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="After offline regression, run bounded checks against the local live stack.",
    )
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    default_report = LIVE_REPORT_PATH if args.live else REPORT_PATH
    selected_report = args.report if args.report is not None else default_report
    destination = (
        selected_report if selected_report.is_absolute()
        else APPSEC_ROOT / selected_report
    )

    try:
        report = build_report(args.timeout)

        if args.live:
            report["live_execution"] = run_live_orchestration(args.timeout)

        write_report(report, destination)

        output = {
            "overall": report["overall"],
            "test_execution": report["execution"]["status"],
            "test_summary": report["execution"]["summary"],
            "coverage": report["coverage"],
            "report": str(destination),
        }
        if args.live:
            output["live_status"] = report["live_execution"]["status"]
            output["live_evidence_directory"] = (
                report["live_execution"]["evidence_directory"]
            )

        print(json.dumps(output, indent=2))

        failed = report["overall"] == "FAIL"
        if args.live:
            failed = failed or report["live_execution"]["status"] in (
                "FAILED", "BLOCKED"
            )
        return 1 if failed else 0

    except Exception as exc:
        print(
            json.dumps({
                "overall": "FAIL",
                "error_type": type(exc).__name__,
            }),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
