
"""
API inventory catalog builder and CSV/JSON export utilities.

Combines:
- OpenAPI-declared endpoints
- Approved API inventory entries
- Runtime-observed endpoints
- Confirmed Shadow API findings
- Confirmed Zombie API findings

Adds discovery-state and OWASP-aligned inventory risk tags.
"""

from __future__ import annotations

import csv
import json

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.inventory import normalize_api_path


CSV_FIELDS = [
    "method",
    "path",
    "operation_id",
    "summary",
    "is_approved",
    "is_declared",
    "runtime_observation_count",
    "discovery_state",
    "risk_rating",
]


RISK_RATINGS = {
    "APPROVED": "LOW",
    "UNAPPROVED": "MEDIUM",
    "SHADOW_API": "HIGH",
    "ZOMBIE_API": "HIGH",
}


def _normalize_findings(
    findings: list[dict[str, Any]] | None,
    expected_status: str,
) -> set[tuple[str, str]]:
    """Extract normalized method/path pairs from confirmed findings."""

    if findings is None:
        return set()

    if not isinstance(findings, list):
        raise ValueError(
            f"{expected_status} findings must be a list."
        )

    normalized = set()

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        method = finding.get("method")
        path = finding.get("route", finding.get("path"))

        if not isinstance(method, str) or not isinstance(path, str):
            continue

        method = method.strip().upper()
        path = normalize_api_path(path)

        if method and path:
            normalized.add((method, path))

    return normalized


def build_inventory_catalog(
    endpoints: list[dict[str, Any]],
    approved_apis: set[tuple[str, str]],
    runtime_events: list[dict[str, Any]] | None = None,
    api_name: str = "Unknown API",
    openapi_version: str | None = None,
    shadow_findings: list[dict[str, Any]] | None = None,
    zombie_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a unified, risk-tagged API inventory catalog."""

    if not isinstance(endpoints, list):
        raise ValueError("Endpoints must be a list.")

    if not isinstance(approved_apis, set):
        raise ValueError("Approved APIs must be a set.")

    if runtime_events is None:
        runtime_events = []

    if not isinstance(runtime_events, list):
        raise ValueError("Runtime events must be a list.")

    shadow_keys = _normalize_findings(
        shadow_findings,
        "Shadow",
    )

    zombie_keys = _normalize_findings(
        zombie_findings,
        "Zombie",
    )

    catalog: dict[tuple[str, str], dict[str, Any]] = {}

    normalized_approved = {
        (method.upper(), normalize_api_path(path))
        for method, path in approved_apis
    }

    # Add approved inventory entries first.
    for method, path in normalized_approved:
        catalog[(method, path)] = {
            "method": method,
            "path": path,
            "operation_id": None,
            "summary": None,
            "is_approved": True,
            "is_declared": False,
            "runtime_observation_count": 0,
        }

    # Add OpenAPI-declared endpoints and preserve metadata.
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue

        method = endpoint.get("method")
        path = endpoint.get("path")

        if not isinstance(method, str) or not isinstance(path, str):
            continue

        method = method.strip().upper()
        path = normalize_api_path(path)

        if not method or not path:
            continue

        key = (method, path)

        record = catalog.setdefault(
            key,
            {
                "method": method,
                "path": path,
                "operation_id": None,
                "summary": None,
                "is_approved": key in normalized_approved,
                "is_declared": False,
                "runtime_observation_count": 0,
            },
        )

        record["is_declared"] = True
        record["is_approved"] = key in normalized_approved
        record["operation_id"] = endpoint.get("operation_id")
        record["summary"] = endpoint.get("summary")

    # Count runtime observations and include runtime-only endpoints.
    for event in runtime_events:
        if not isinstance(event, dict):
            continue

        method = event.get("method")
        path = event.get("path")

        if not isinstance(method, str) or not isinstance(path, str):
            continue

        method = method.strip().upper()
        path = normalize_api_path(path)

        if not method or not path:
            continue

        key = (method, path)

        record = catalog.setdefault(
            key,
            {
                "method": method,
                "path": path,
                "operation_id": None,
                "summary": None,
                "is_approved": key in normalized_approved,
                "is_declared": False,
                "runtime_observation_count": 0,
            },
        )

        record["runtime_observation_count"] += 1

    records = []

    for key in sorted(catalog):
        record = catalog[key]

        # Confirmed Zombie finding has highest priority.
        if key in zombie_keys:
            state = "ZOMBIE_API"

        # Confirmed Shadow finding comes next.
        elif key in shadow_keys:
            state = "SHADOW_API"

        elif not record["is_approved"] and record["is_declared"]:
            state = "UNAPPROVED"

        elif record["is_approved"]:
            state = "APPROVED"

        else:
            # Runtime-only endpoints remain Shadow candidates.
            # A confirmed finding is required for SHADOW_API.
            state = "UNCLASSIFIED"

        records.append({
            **record,
            "discovery_state": state,
            "risk_rating": RISK_RATINGS.get(
                state,
                "UNASSESSED",
            ),
        })

    state_counts = Counter(
        record["discovery_state"] for record in records
    )

    risk_counts = Counter(
        record["risk_rating"] for record in records
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_name": api_name,
        "openapi_version": openapi_version,
        "total_endpoints": len(records),
        "approved_endpoints": state_counts.get("APPROVED", 0),
        "unapproved_endpoints": state_counts.get("UNAPPROVED", 0),
        "shadow_endpoints": state_counts.get("SHADOW_API", 0),
        "zombie_endpoints": state_counts.get("ZOMBIE_API", 0),
        "unclassified_endpoints": state_counts.get("UNCLASSIFIED", 0),
        "risk_summary": dict(risk_counts),
        "total_runtime_observations": sum(
            record["runtime_observation_count"]
            for record in records
        ),
        "endpoints": records,
    }


def export_inventory_catalog(
    catalog: dict[str, Any],
    json_path: str | Path = "reports/api_inventory.json",
    csv_path: str | Path = "reports/api_inventory.csv",
) -> tuple[str, str]:
    """Export the inventory catalog to JSON and CSV."""

    if not isinstance(catalog, dict):
        raise ValueError("Inventory catalog must be a dictionary.")

    endpoints = catalog.get("endpoints")

    if not isinstance(endpoints, list):
        raise ValueError("Catalog must contain an endpoints list.")

    json_output = Path(json_path)
    csv_output = Path(csv_path)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    with json_output.open("w", encoding="utf-8") as file:
        json.dump(
            catalog,
            file,
            indent=4,
            ensure_ascii=False,
        )

    with csv_output.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(endpoints)

    return str(json_output), str(csv_output)
