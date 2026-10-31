
"""
API inventory catalog builder and CSV/JSON export utilities.

Combines:
- OpenAPI-declared endpoints
- Approved API inventory entries
- Runtime-observed endpoints

The same catalog records are written to JSON and CSV.
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
]


def build_inventory_catalog(
    endpoints: list[dict[str, Any]],
    approved_apis: set[tuple[str, str]],
    runtime_events: list[dict[str, Any]] | None = None,
    api_name: str = "Unknown API",
    openapi_version: str | None = None,
) -> dict[str, Any]:
    """Build a unified API inventory catalog."""

    if not isinstance(endpoints, list):
        raise ValueError("Endpoints must be a list.")

    if not isinstance(approved_apis, set):
        raise ValueError("Approved APIs must be a set.")

    if runtime_events is None:
        runtime_events = []

    if not isinstance(runtime_events, list):
        raise ValueError("Runtime events must be a list.")

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

        if not method:
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

        if not method:
            continue

        path = normalize_api_path(path)
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

        if not record["is_declared"] and not record["is_approved"]:
            state = "SHADOW_API"
        elif not record["is_approved"]:
            state = "UNAPPROVED"
        else:
            state = "APPROVED"

        records.append({
            **record,
            "discovery_state": state,
        })

    state_counts = Counter(
        record["discovery_state"] for record in records
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_name": api_name,
        "openapi_version": openapi_version,
        "total_endpoints": len(records),
        "approved_endpoints": state_counts.get("APPROVED", 0),
        "unapproved_endpoints": state_counts.get("UNAPPROVED", 0),
        "shadow_endpoints": state_counts.get("SHADOW_API", 0),
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
