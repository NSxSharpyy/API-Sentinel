
"""
Parameter Drift Detection Engine for API-Sentinel.

Compares observed runtime request and response JSON payloads
against the schemas defined in an official OpenAPI specification.

Only officially documented endpoints are evaluated.

Undocumented fields are reported as review findings.
"""

from __future__ import annotations

import re
from typing import Any


HTTP_METHODS = {
    "GET", "POST", "PUT", "PATCH",
    "DELETE", "OPTIONS", "HEAD", "TRACE",
}


def normalize_path(path: str) -> str:
    """Normalize a route before matching."""

    path = path.split("?", 1)[0].strip()

    if not path.startswith("/"):
        path = "/" + path

    if path != "/":
        path = path.rstrip("/")

    return path


def path_to_regex(path: str) -> re.Pattern[str]:
    """Convert OpenAPI route templates into regex matchers."""

    escaped = re.escape(normalize_path(path))

    escaped = re.sub(
        r"\\\{[^{}]+\\\}",
        r"[^/]+",
        escaped,
    )

    return re.compile("^" + escaped + "$")


def resolve_schema_ref(
    schema: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Resolve local OpenAPI component schema references."""

    reference = schema.get("$ref")

    if not isinstance(reference, str):
        return schema

    if not reference.startswith("#/"):
        return schema

    current: Any = spec

    try:
        for part in reference[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            current = current[part]

    except (KeyError, TypeError):
        return schema

    if not isinstance(current, dict):
        return schema

    return current


def get_json_schema(
    container: Any,
) -> dict[str, Any] | None:
    """Extract an application/json schema from an OpenAPI container."""

    if not isinstance(container, dict):
        return None

    content = container.get("content")

    if not isinstance(content, dict):
        return None

    json_content = content.get("application/json")

    if not isinstance(json_content, dict):
        return None

    schema = json_content.get("schema")

    if isinstance(schema, dict):
        return schema

    return None


def get_request_schema(
    operation: dict[str, Any],
) -> dict[str, Any] | None:
    """Get the documented JSON request body schema."""

    request_body = operation.get("requestBody")

    return get_json_schema(request_body)


def get_response_schema(
    operation: dict[str, Any],
) -> dict[str, Any] | None:
    """Get the documented successful JSON response schema."""

    responses = operation.get("responses", {})

    if not isinstance(responses, dict):
        return None

    successful_codes = sorted(
        (
            code for code in responses
            if isinstance(code, str)
            and (
                code.startswith("2")
                or code == "2XX"
            )
        ),
        key=lambda code: (code == "2XX", code),
    )

    for code in successful_codes:
        schema = get_json_schema(responses[code])

        if schema is not None:
            return schema

    return None


def find_undocumented_fields(
    observed: Any,
    schema: dict[str, Any],
    spec: dict[str, Any],
    location: str,
    field_prefix: str = "",
) -> list[dict[str, str]]:
    """
    Recursively identify observed JSON object fields
    absent from the official OpenAPI schema.
    """

    findings: list[dict[str, str]] = []

    schema = resolve_schema_ref(schema, spec)

    if not isinstance(observed, dict):
        if isinstance(observed, list):
            item_schema = schema.get("items")

            if isinstance(item_schema, dict):
                for index, item in enumerate(observed):
                    findings.extend(
                        find_undocumented_fields(
                            item,
                            item_schema,
                            spec,
                            location,
                            f"{field_prefix}[{index}]",
                        )
                    )

        return findings

    properties = schema.get("properties", {})

    if not isinstance(properties, dict):
        properties = {}

    for field_name, field_value in observed.items():

        field_path = (
            f"{field_prefix}.{field_name}"
            if field_prefix
            else str(field_name)
        )

        if field_name not in properties:

            findings.append({
                "field": field_path,
                "location": location,
                "drift_type": "undocumented_field",
            })

            continue

        child_schema = properties[field_name]

        if isinstance(child_schema, dict):
            findings.extend(
                find_undocumented_fields(
                    field_value,
                    child_schema,
                    spec,
                    location,
                    field_path,
                )
            )

    return findings


def match_operation(
    method: str,
    path: str,
    spec: dict[str, Any],
) -> dict[str, Any] | None:
    """Find the official OpenAPI operation matching a runtime event."""

    method = method.upper().strip()
    path = normalize_path(path)

    if method not in HTTP_METHODS:
        return None

    paths = spec.get("paths", {})

    if not isinstance(paths, dict):
        return None

    for route, operations in paths.items():

        if not isinstance(route, str):
            continue

        if not isinstance(operations, dict):
            continue

        matcher = path_to_regex(route)

        if not matcher.fullmatch(path):
            continue

        operation = operations.get(method.lower())

        if isinstance(operation, dict):
            return operation

    return None


def detect_parameter_drift(
    spec: dict[str, Any],
    runtime_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare runtime payloads against official OpenAPI schemas.

    Events without request or response payloads are skipped
    for the corresponding comparison.
    """

    findings: list[dict[str, Any]] = []
    checked_events = 0

    for event in runtime_events:

        method = str(event.get("method", "")).upper().strip()
        path = event.get("path", "")

        if (
            method not in HTTP_METHODS
            or not isinstance(path, str)
            or not path.strip()
        ):
            continue

        operation = match_operation(method, path, spec)

        # Only officially known endpoints are evaluated.
        if operation is None:
            continue

        checked_events += 1

        comparisons = (
            ("request", get_request_schema(operation)),
            ("response", get_response_schema(operation)),
        )

        for location, schema in comparisons:

            # Do not interpret missing payloads as empty objects.
            if location not in event:
                continue

            if schema is None:
                continue

            payload = event[location]

            if not isinstance(payload, (dict, list)):
                continue

            field_findings = find_undocumented_fields(
                payload,
                schema,
                spec,
                location,
            )

            for finding in field_findings:
                findings.append({
                    "method": method,
                    "path": normalize_path(path),
                    **finding,
                    "status": "needs_review",
                })

    return {
        "summary": {
            "total_runtime_events_checked": checked_events,
            "total_drift_findings": len(findings),
            "undocumented_request_fields": sum(
                item["location"] == "request"
                for item in findings
            ),
            "undocumented_response_fields": sum(
                item["location"] == "response"
                for item in findings
            ),
        },
        "findings": findings,
    }
