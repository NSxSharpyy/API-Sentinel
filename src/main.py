from pathlib import Path
import argparse
import json
import re

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


def parse_openapi_spec(file_path: str) -> dict:
    """Load and validate an OpenAPI JSON specification."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Specification not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            "The supplied specification path is not a file."
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            spec = json.load(file)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid JSON OpenAPI specification."
        ) from exc

    if not isinstance(spec, dict):
        raise ValueError(
            "The specification must be a JSON object."
        )

    if not isinstance(spec.get("openapi"), str):
        raise ValueError(
            "Missing or invalid OpenAPI version field."
        )

    if not isinstance(spec.get("paths", {}), dict):
        raise ValueError(
            "The 'paths' field must be a JSON object."
        )

    if not isinstance(spec.get("info"), dict):
        raise ValueError(
            "The 'info' field must be a JSON object."
        )

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

        # Convert {id} parameters into a single path segment.
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


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "API-Sentinel: Shadow API and runtime endpoint detection"
        )
    )

    parser.add_argument(
        "--spec",
        default="samples/openapi.json",
        help="Path to the OpenAPI JSON specification",
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

    args = parser.parse_args()

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

            print(
                f"Runtime report saved to: {runtime_report}"
            )

            for finding in runtime_findings:

                print(
                    f"[REVIEW] {finding['method']} "
                    f"{finding['path']}"
                )

        else:

            print(
                "\nRuntime detection skipped: "
                f"{runtime_log_path} was not found."
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