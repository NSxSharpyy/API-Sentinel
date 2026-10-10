""" Runtime BOLO engine for API-Sentinel. Compares API endpoints observed in a JSON Lines runtime log against an approved OpenAPI JSON specification. Unmatched endpoints are reported as potential review findings; they are not automatically classified as vulnerabilities. Expected runtime log format (one JSON object per line): {"method": "GET", "path": "/users"} {"method": "DELETE", "path": "/users/42"} Usage from the project root: python -m src.runtime --spec approved_apis.json --logs runtime_logs.jsonl The OpenAPI specification should be a JSON file containing a "paths" object. """

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HTTP_METHODS = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
    "TRACE",
}


def load_openapi_spec(spec_path: str | Path) -> dict[str, Any]:
    """Load and minimally validate an OpenAPI JSON specification."""
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"OpenAPI specification not found: {path}")
    if not path.is_file():
        raise ValueError(f"The specification path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            spec = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON in OpenAPI specification.") from exc

    if not isinstance(spec, dict):
        raise ValueError("The OpenAPI specification must be a JSON object.")

    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise ValueError('The OpenAPI specification must contain a "paths" object.')

    return spec


def normalize_path(path: str) -> str:
    """Normalize a URL path for comparison, ignoring query strings/trailing slash."""
    path = path.split("?", 1)[0].strip()
    if not path.startswith("/"):
        path = "/" + path
    if path != "/":
        path = path.rstrip("/")
    return path


def _openapi_path_to_regex(path: str) -> re.Pattern[str]:
    """Convert an OpenAPI template such as /users/{userId} into a matcher."""
    escaped = re.escape(normalize_path(path))
    escaped = re.sub(r"\\\{[^{}]+\\\}", r"[^/]+", escaped)
    return re.compile(r"^" + escaped + r"$")


def build_approved_endpoints(spec: dict[str, Any]) -> list[tuple[str, re.Pattern[str], str]]:
    """Return approved method/path matchers from an OpenAPI specification."""
    approved: list[tuple[str, re.Pattern[str], str]] = []

    for route, operations in spec.get("paths", {}).items():
        if not isinstance(route, str) or not isinstance(operations, dict):
            continue
        for method, details in operations.items():
            method_upper = method.upper()
            if method_upper not in HTTP_METHODS:
                continue
            summary = ""
            if isinstance(details, dict):
                summary = str(details.get("summary", ""))
            approved.append(
                (method_upper, _openapi_path_to_regex(route), summary)
            )

    return approved


def load_runtime_events(log_path: str | Path) -> list[dict[str, str]]:
    """Read JSON Lines runtime events containing method and path fields."""
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Runtime log file not found: {path}")
    if not path.is_file():
        raise ValueError(f"The runtime log path is not a file: {path}")

    events: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in runtime log at line {line_number}."
                ) from exc

            if not isinstance(event, dict):
                raise ValueError(
                    f"Runtime log line {line_number} must be a JSON object."
                )

            method = str(event.get("method", "")).upper().strip()
            endpoint = event.get("path", event.get("url", ""))
            if not method or not isinstance(endpoint, str) or not endpoint.strip():
                # Ignore records that do not describe an HTTP endpoint.
                continue
            if method not in HTTP_METHODS:
                continue

            events.append({"method": method, "path": normalize_path(endpoint)})

    return events


def find_unapproved_endpoints( events: list[dict[str, str]], approved: list[tuple[str, re.Pattern[str], str]], ) -> list[dict[str, str]]:
    """Return unique observed method/path pairs absent from the approved spec."""
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for event in events:
        method = event["method"].upper()
        endpoint = normalize_path(event["path"])
        key = (method, endpoint)

        if key in seen:
            continue
        seen.add(key)

        is_approved = any(
            method == approved_method and matcher.fullmatch(endpoint)
            for approved_method, matcher, _summary in approved
        )
        if not is_approved:
            findings.append(
                {
                    "method": method,
                    "path": endpoint,
                    "classification": "potential_unapproved_endpoint",
                    "status": "needs_review",
                }
            )

    return findings


def save_findings( findings: list[dict[str, str]], output_path: str | Path = "reports/runtime_bolo_findings.json", ) -> str:
    """Write findings to a JSON report and return its path."""
    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "total_findings": len(findings),
        "findings": findings,
    }
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    return str(report_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare observed runtime API endpoints with an approved OpenAPI spec."
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="Path to an approved OpenAPI JSON specification.",
    )
    parser.add_argument(
        "--logs",
        required=True,
        help="Path to a JSON Lines runtime log file.",
    )
    parser.add_argument(
        "--output",
        default="reports/runtime_bolo_findings.json",
        help="Output JSON report path (default: reports/runtime_bolo_findings.json).",
    )
    args = parser.parse_args()

    try:
        spec = load_openapi_spec(args.spec)
        approved = build_approved_endpoints(spec)
        events = load_runtime_events(args.logs)
        findings = find_unapproved_endpoints(events, approved)
        report_path = save_findings(findings, args.output)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"Approved endpoint templates loaded: {len(approved)}")
    print(f"Runtime endpoint events loaded: {len(events)}")
    print(f"Potential endpoints needing review: {len(findings)}")
    print(f"Report saved to: {report_path}")

    for finding in findings:
        print(
            f"[REVIEW] {finding['method']} {finding['path']} "
            f"({finding['classification']})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())