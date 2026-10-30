
from pathlib import Path
import argparse
import json
import re

import yaml  # type: ignore

from src.repo_crawler import (
    discover_openapi_files,
    fetch_openapi_spec,
    extract_api_contracts,
    save_api_contracts,
)

from src.inventory import (
    load_approved_apis,
    find_unapproved_apis,
)

from src.reporter import save_findings

from src.runtime import (
    load_runtime_events,
    find_unapproved_endpoints,
    save_findings as save_runtime_findings,
)

from src.parameter_drift import detect_parameter_drift


def parse_openapi_spec(file_path: str) -> dict:
    """Load and validate an OpenAPI JSON or YAML specification."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Specification not found: {path}")

    if not path.is_file():
        raise ValueError("The supplied specification path is not a file.")

    suffix = path.suffix.lower()

    try:
        # Supports UTF-8 files with or without BOM.
        with path.open("r", encoding="utf-8-sig") as file:
            if suffix == ".json":
                spec = json.load(file)
            elif suffix in {".yaml", ".yml"}:
                spec = yaml.safe_load(file)
            else:
                raise ValueError(
                    f"Unsupported specification format: {suffix}. "
                    "Use .json, .yaml, or .yml."
                )

    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(
            "Invalid JSON or YAML OpenAPI specification."
        ) from exc

    if not isinstance(spec, dict):
        raise ValueError(
            "The specification must be a JSON object or YAML mapping."
        )

    if not isinstance(spec.get("openapi"), str):
        raise ValueError("Missing or invalid OpenAPI version field.")

    if "paths" not in spec:
        raise ValueError(
            "Invalid OpenAPI specification: required 'paths' field is missing."
        )

    if not isinstance(spec["paths"], dict):
        raise ValueError("The 'paths' field must be a mapping/object.")

    if not isinstance(spec.get("info"), dict):
        raise ValueError("The 'info' field must be a mapping/object.")

    return spec


def extract_endpoints(spec: dict) -> list[dict]:
    """Extract HTTP endpoints from an OpenAPI specification."""

    endpoints = []

    http_methods = {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "options",
        "head",
        "trace",
    }

    for route, details in spec.get("paths", {}).items():

        if not isinstance(details, dict):
            continue

        for method, operation in details.items():

            if method.lower() not in http_methods:
                continue

            if not isinstance(operation, dict):
                operation = {}

            endpoints.append({
                "path": route,
                "method": method.upper(),
                "operation_id": operation.get("operationId"),
                "summary": operation.get("summary"),
            })

    return endpoints


def build_approved_runtime_endpoints(
    approved: set[tuple[str, str]],
) -> list[tuple[str, re.Pattern, str]]:
    """Build regex patterns for approved runtime endpoints."""

    approved_endpoints = []

    for method, path in approved:

        escaped_path = re.escape(path)

        # Convert templates such as /users/{id} into one path segment.
        pattern = re.sub(
            r"\\\{[^{}]+\\\}",
            r"[^/]+",
            escaped_path,
        )

        approved_endpoints.append((
            method.upper(),
            re.compile(f"^{pattern}$"),
            "",
        ))

    return approved_endpoints


def save_parameter_drift_report(
    report: dict,
    output_path: str,
) -> str:
    """Save parameter drift findings and summary as JSON."""

    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    return str(report_path)


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "API-Sentinel: Shadow API and runtime endpoint detection"
        )
    )

    parser.add_argument(
        "--spec",
        default="samples/openapi.json",
        help="Path to the OpenAPI JSON or YAML specification",
    )

    parser.add_argument(
        "--repo-owner",
        help="GitHub repository owner",
    )

    parser.add_argument(
        "--repo-name",
        help="GitHub repository name",
    )

    parser.add_argument(
        "--repo-branch",
        default="main",
        help="GitHub repository branch (default: main)",
    )

    parser.add_argument(
        "--inventory",
        default="samples/approved_apis.json",
        help="Path to the approved API inventory",
    )

    parser.add_argument(
        "--runtime-log",
        default="runtime_logs.jsonl",
        help="Path to the runtime JSONL log file",
    )

    parser.add_argument(
        "--static-report",
        default="reports/shadow_api_findings.json",
        help="Output path for static findings",
    )

    parser.add_argument(
        "--runtime-report",
        default="reports/runtime_bolo_findings.json",
        help="Output path for runtime findings",
    )

    parser.add_argument(
        "--drift-report",
        default="reports/parameter_drift_findings.json",
        help="Output path for parameter drift findings",
    )

    args = parser.parse_args()

    # ==========================================
    # PHASE 0: REPOSITORY CONTRACT DISCOVERY
    # ==========================================

    if args.repo_owner and args.repo_name:
        try:
            discovered_files = discover_openapi_files(
                args.repo_owner,
                args.repo_name,
                args.repo_branch,
            )

            print("\n=== API-Sentinel: Repository Contract Crawler ===")
            print(f"Repository: {args.repo_owner}/{args.repo_name}")
            print(f"Branch: {args.repo_branch}")
            print(f"OpenAPI files discovered: {len(discovered_files)}")

            all_contracts = []

            for file_path in discovered_files:
                print(f"[FETCH] {file_path}")

                spec = fetch_openapi_spec(
                    args.repo_owner,
                    args.repo_name,
                    args.repo_branch,
                    file_path,
                )

                contracts = extract_api_contracts(spec)

                for contract in contracts:
                    contract["source_file"] = file_path

                all_contracts.extend(contracts)

            save_api_contracts(all_contracts)

            print(f"Extracted API contracts: {len(all_contracts)}")

        except RuntimeError as error:
            print(f"Repository crawler error: {error}")
            return

    try:

        # ==========================================
        # PHASE 1: STATIC SHADOW API DETECTION
        # ==========================================

        spec = parse_openapi_spec(args.spec)

        endpoints = extract_endpoints(spec)

        approved = load_approved_apis(args.inventory)

        unapproved = find_unapproved_apis(
            endpoints,
            approved,
        )

        print("\n=== API-Sentinel: Static Detection ===")

        print(
            f"API: {spec.get('info', {}).get('title', 'Unknown API')}"
        )

        print(f"Discovered endpoints: {len(endpoints)}")
        print(f"Approved endpoints: {len(approved)}")
        print(f"Unapproved endpoints: {len(unapproved)}")

        if unapproved:
            print("\nPotential Shadow API Findings:")

            for api in unapproved:
                print(
                    f"[REVIEW] {api['method']} {api['path']} "
                    f"- {api.get('summary') or 'No summary'}"
                )
        else:
            print("\nNo unapproved endpoints found.")

        static_report = save_findings(
            unapproved,
            args.static_report,
        )

        print(f"\nStatic report saved to: {static_report}")

        # ==========================================
        # PHASE 2: RUNTIME BOLO DETECTION
        # ==========================================

        runtime_log_path = Path(args.runtime_log)

        if runtime_log_path.is_file():

            runtime_events = load_runtime_events(
                str(runtime_log_path)
            )

            approved_runtime_endpoints = (
                build_approved_runtime_endpoints(approved)
            )

            runtime_findings = find_unapproved_endpoints(
                runtime_events,
                approved_runtime_endpoints,
            )

            runtime_report = save_runtime_findings(
                runtime_findings,
                args.runtime_report,
            )

            print("\n=== API-Sentinel: Runtime BOLO Detection ===")
            print(f"Runtime events: {len(runtime_events)}")
            print(f"Potential findings: {len(runtime_findings)}")
            print(f"Runtime report saved to: {runtime_report}")

            for finding in runtime_findings:
                print(
                    f"[REVIEW] {finding['method']} "
                    f"{finding['path']}"
                )

            # ==========================================
            # PHASE 3: PARAMETER DRIFT DETECTION
            # ==========================================

            drift_report = detect_parameter_drift(
                spec,
                runtime_events,
            )

            drift_report_path = save_parameter_drift_report(
                drift_report,
                args.drift_report,
            )

            print("\n=== API-Sentinel: Parameter Drift Detection ===")

            # Summary counters are nested inside report["summary"].
            summary = drift_report.get("summary", {})

            print(
                "Runtime events checked: "
                f"{summary.get('total_runtime_events_checked', 0)}"
            )

            print(
                "Total drift findings: "
                f"{summary.get('total_drift_findings', 0)}"
            )

            print(
                "Undocumented request fields: "
                f"{summary.get('undocumented_request_fields', 0)}"
            )

            print(
                "Undocumented response fields: "
                f"{summary.get('undocumented_response_fields', 0)}"
            )

            print(
                f"Parameter drift report saved to: {drift_report_path}"
            )

            for finding in drift_report.get("findings", []):
                print(
                    f"[DRIFT] {finding.get('method')} "
                    f"{finding.get('path')} | "
                    f"{finding.get('location')} | "
                    f"{finding.get('field')}"
                )

        else:

            print(
                "\nRuntime detection skipped: "
                f"{runtime_log_path} was not found."
            )

            print(
                "Parameter drift detection skipped because "
                "runtime events are unavailable."
            )

    except (
        FileNotFoundError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as error:

        print(f"Error: {error}")


if __name__ == "__main__":
    main()
