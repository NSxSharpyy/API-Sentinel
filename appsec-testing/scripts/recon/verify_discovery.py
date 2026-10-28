#!/usr/bin/env python3
"""Grade discovery output against the Day 10 shadow/zombie manifest."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SERVICES = {"auth", "user", "order", "billing"}
METHODS = {"GET", "POST", "PUT", "DELETE"}
CLASSIFICATIONS = {"shadow", "zombie", "documented", "unknown"}

MANIFEST_DEFAULT = ROOT / "docs/shadow_zombie_manifest.md"
MOCK_DEFAULT = ROOT / "scripts/recon/mock_member3_discovery_output.json"
DAY11_DEFAULT = ROOT / "logs/discovery_report.json"


def normalize_path(path):
    """Normalize numeric path segments representing resource IDs."""
    return re.sub(r"(?<=/)\d+(?=/|$)", "{id}", path)


def normalize_key(key):
    """Normalize an endpoint tuple while preserving service and method."""
    service, method, route = key
    return service, method, normalize_path(route)

# Exact documented routes used to identify documented-route false positives.
DOCUMENTED_V2_ROUTES = {
    ("auth", "POST", "/api/v2/auth/login"),
    ("auth", "GET", "/api/v2/auth/verify"),
    ("user", "GET", "/api/v2/users/me"),
    ("order", "GET", "/api/v2/orders"),
    ("order", "GET", "/api/v2/orders/1"),
    ("billing", "GET", "/api/v2/billing/invoices"),
    ("billing", "GET", "/api/v2/billing/invoices/1"),
}


def load_manifest(path):
    """Read ground truth from the Markdown table, not from scanner output."""
    if not path.is_file():
        raise ValueError(f"Ground-truth manifest not found: {path}")

    ground_truth = {}
    pattern = re.compile(
        r"^\|\s*(auth|user|order|billing)\s*\|\s*"
        r"(GET|POST|PUT|DELETE)\s*\|\s*(/[^|]*)\s*\|\s*"
        r"(shadow|zombie)\s*\|",
        re.IGNORECASE,
    )

    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        service, method, route, category = match.groups()
        key = (service.lower(), method.upper(), route.strip())
        if key in ground_truth:
            raise ValueError(f"Duplicate endpoint in manifest: {key}")
        ground_truth[key] = category.lower()

    if not ground_truth:
        raise ValueError(f"No ground-truth endpoints parsed from {path}")

    return ground_truth


def validate_report(data):
    """Validate the report and return valid findings plus validation errors."""
    errors = []

    if not isinstance(data, dict):
        raise ValueError("Top-level JSON value must be an object")

    timestamp = data.get("scan_timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        errors.append("'scan_timestamp' must be a non-empty ISO 8601 string")
    else:
        try:
            datetime.fromisoformat(timestamp.strip().replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"Invalid ISO 8601 scan_timestamp: {timestamp!r}")

    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("'findings' must be a JSON array")

    valid = []
    seen = set()
    required = {"service", "method", "path", "classification", "confidence"}

    for index, item in enumerate(findings):
        prefix = f"findings[{index}]"

        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue

        missing = required - item.keys()
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(sorted(missing))}")
            continue

        service = item["service"]
        method = item["method"]
        route = item["path"]
        category = item["classification"]
        confidence = item["confidence"]

        problems = []
        if not isinstance(service, str) or service not in SERVICES:
            problems.append(f"invalid service {service!r}")
        if not isinstance(method, str) or method not in METHODS:
            problems.append(f"invalid method {method!r}")
        if (
            not isinstance(route, str)
            or not route.startswith("/")
            or "?" in route
            or "#" in route
            or "://" in route
            or any(char.isspace() for char in route)
        ):
            problems.append(f"invalid path {route!r}")
        if not isinstance(category, str) or category not in CLASSIFICATIONS:
            problems.append(f"invalid classification {category!r}")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            problems.append(f"confidence must be a number from 0 to 1, got {confidence!r}")

        if problems:
            errors.append(f"{prefix}: " + "; ".join(problems))
            continue

        key = normalize_key((service, method, route))
        if key in seen:
            errors.append(f"{prefix}: duplicate endpoint tuple {key}")
            continue

        seen.add(key)
        valid.append({
            "service": service,
            "method": method,
            "path": route,
            "classification": category,
            "confidence": confidence,
        })

    return valid, errors


def grade(report_path, manifest_path, output_path=None):
    ground_truth = load_manifest(manifest_path)

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {report_path}: {exc}") from exc

    findings, validation_errors = validate_report(data)

    # Normalize paths for comparisons, but retain canonical manifest paths
    # for reporting missed endpoints.
    reported = {}
    reported_original_keys = {}
    for finding in findings:
        original_key = (
            finding["service"], finding["method"], finding["path"]
        )
        key = normalize_key(original_key)
        reported[key] = finding
        reported_original_keys[key] = original_key

    normalized_ground_truth = {
        normalize_key(key): key for key in ground_truth
    }
    found_normalized = set(reported) & set(normalized_ground_truth)
    found_keys = {
        normalized_ground_truth[key] for key in found_normalized
    }
    missed_keys = set(ground_truth) - found_keys

    classification_errors = [
        (canonical_key, reported[normalize_key(canonical_key)]["classification"], expected)
        for canonical_key, expected in ground_truth.items()
        if normalize_key(canonical_key) in reported
        and reported[normalize_key(canonical_key)]["classification"] != expected
    ]

    normalized_documented_routes = {
        normalize_key(key) for key in DOCUMENTED_V2_ROUTES
    }

    # Correctly labelled documented routes are not false positives.
    false_positive_normalized = {
        key for key in reported
        if key not in normalized_ground_truth
        and not (
            key in normalized_documented_routes
            and reported[key]["classification"] == "documented"
        )
    }
    false_positive_keys = {
        reported_original_keys[key] for key in false_positive_normalized
    }

    recall = len(found_keys) / len(ground_truth) if ground_truth else 0.0
    denominator = len(found_keys) + len(false_positive_keys)
    precision = len(found_keys) / denominator if denominator else 0.0

    passed = (
        not validation_errors
        and not missed_keys
        and not false_positive_keys
        and not classification_errors
        and recall == 1.0
        and precision == 1.0
    )

    print("=== Shadow/Zombie Discovery Verification ===")
    print(f"Input: {report_path}")
    print(f"Ground-truth manifest: {manifest_path}")
    print(f"Ground-truth endpoints: {len(ground_truth)}")
    print(f"Valid unique findings: {len(findings)}")
    print(f"Endpoints found: {len(found_keys)}/{len(ground_truth)}")
    print(f"Endpoint recall: {recall:.1%}")
    print(f"False positives: {len(false_positive_keys)}")
    print(f"Precision: {precision:.1%}")
    print(f"Classification errors: {len(classification_errors)}")
    print(f"Validation errors: {len(validation_errors)}")

    if missed_keys:
        print("\nMISSED ENDPOINTS:")
        for service, method, route in sorted(missed_keys):
            print(f"  - {service} {method} {route} [{ground_truth[(service, method, route)]}]")

    if false_positive_keys:
        print("\nFALSE POSITIVES / UNVERIFIED FINDINGS:")
        for service, method, route in sorted(false_positive_keys):
            marker = " (documented route)" if normalize_key(
                (service, method, route)
            ) in normalized_documented_routes else ""
            print(f"  - {service} {method} {route}{marker}")

    if classification_errors:
        print("\nCLASSIFICATION ERRORS:")
        for key, actual, expected in classification_errors:
            print(f"  - {key}: reported {actual!r}, expected {expected!r}")

    if validation_errors:
        print("\nVALIDATION ERRORS:")
        for error in validation_errors:
            print(f"  - {error}")

    exit_code = 0 if passed else 1

    # Machine-readable results; keep the CLI exit-code contract unchanged.
    missed_endpoints = [
        {
            "service": service,
            "method": method,
            "path": route,
            "expected_classification": ground_truth[(service, method, route)],
        }
        for service, method, route in sorted(missed_keys)
    ]

    false_positives = [
        {
            "service": service,
            "method": method,
            "path": route,
            "documented_route": normalize_key(
                (service, method, route)
            ) in normalized_documented_routes,
        }
        for service, method, route in sorted(false_positive_keys)
    ]

    classification_error_details = [
        {
            "service": key[0],
            "method": key[1],
            "path": key[2],
            "reported_classification": actual,
            "expected_classification": expected,
        }
        for key, actual, expected in classification_errors
    ]

    per_endpoint = []
    for key, expected in sorted(ground_truth.items()):
        normalized = normalize_key(key)
        finding = reported.get(normalized)
        per_endpoint.append({
            "service": key[0],
            "method": key[1],
            "path": key[2],
            "expected_classification": expected,
            "found": normalized in reported,
            "reported_classification": (
                finding["classification"] if finding else None
            ),
            "classification_correct": (
                finding["classification"] == expected if finding else False
            ),
        })

    machine_report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "input_report": str(report_path),
        "manifest": str(manifest_path),
        "verdict": "PASS" if passed else "FAIL",
        "exit_code": exit_code,
        "ground_truth_endpoints": len(ground_truth),
        "valid_unique_findings": len(findings),
        "matched_endpoints": len(found_keys),
        "recall": recall,
        "false_positive_count": len(false_positive_keys),
        "false_positives": false_positives,
        "precision": precision,
        "classification_error_count": len(classification_errors),
        "classification_errors": classification_error_details,
        "validation_error_count": len(validation_errors),
        "validation_errors": validation_errors,
        "missed_endpoints": missed_endpoints,
        "per_endpoint": per_endpoint,
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(machine_report, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report: {output_path}")

    print(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
    return exit_code


def compare_day11(report_path, day11_path):
    """Optional context comparison; Day 11 findings are not ground truth."""
    if not day11_path.is_file():
        print(f"\nDay 11 comparison skipped: {day11_path} not found")
        return

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        day11 = json.loads(day11_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"\nDay 11 comparison skipped: {exc}")
        return

    findings = data.get("findings", [])
    if not isinstance(findings, list):
        print("\nDay 11 comparison skipped: input findings are malformed")
        return

    mock_paths = {
        (item.get("service"), item.get("path"))
        for item in findings if isinstance(item, dict)
    }
    by_service = day11.get("by_service", {})
    day11_paths = {
        (service, path)
        for service, paths in by_service.items()
        if isinstance(paths, list)
        for path in paths
    }

    print("\n=== Day 11 Scan Comparison (context only) ===")
    print("Shared service/path pairs:", len(mock_paths & day11_paths))
    print("In mock/report but not Day 11:", len(mock_paths - day11_paths))
    print("In Day 11 but not mock/report:", len(day11_paths - mock_paths))
    print("Note: scanner output is not ground truth.")


def main():
    parser = argparse.ArgumentParser(
        description="Verify Member 3 discovery output against the Day 10 manifest."
    )
    parser.add_argument(
        "--discovery-output", type=Path, default=MOCK_DEFAULT,
        help="Path to a discovery report JSON (default: temporary mock)",
    )
    parser.add_argument(
        "--manifest", type=Path, default=MANIFEST_DEFAULT,
        help="Path to the ground-truth Markdown manifest",
    )
    parser.add_argument(
        "--day11-report", type=Path, default=DAY11_DEFAULT,
        help="Optional Day 11 scan report used for context only",
    )
    parser.add_argument(
        "--skip-day11", action="store_true",
        help="Skip the optional Day 11 comparison",
    )
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "logs/discovery_verification_report.json",
        help="Path for the machine-readable verification JSON report",
    )
    args = parser.parse_args()

    try:
        result = grade(args.discovery_output, args.manifest, args.out)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.skip_day11:
        compare_day11(args.discovery_output, args.day11_report)

    return result


if __name__ == "__main__":
    raise SystemExit(main())
