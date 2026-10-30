
"""
Dynamic OpenAPI 3.0 schema generator for API-Sentinel.

Builds OpenAPI schemas from observed JSON request and response payloads.
"""

from __future__ import annotations

from typing import Any


HTTP_METHODS = {
    "GET", "POST", "PUT", "PATCH",
    "DELETE", "OPTIONS", "HEAD", "TRACE",
}


def infer_schema(value: Any) -> dict[str, Any]:
    """Infer an OpenAPI-compatible schema from a Python value."""

    if value is None:
        return {"nullable": True}

    if isinstance(value, bool):
        return {"type": "boolean"}

    if isinstance(value, int):
        return {"type": "integer"}

    if isinstance(value, float):
        return {"type": "number"}

    if isinstance(value, str):
        return {"type": "string"}

    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {}}

        item_schema = infer_schema(value[0])

        for item in value[1:]:
            item_schema = merge_schemas(
                item_schema,
                infer_schema(item),
            )

        return {
            "type": "array",
            "items": item_schema,
        }

    if isinstance(value, dict):
        properties = {
            key: infer_schema(item)
            for key, item in value.items()
        }

        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
        }

    return {}


def merge_schemas(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """Merge schemas inferred from multiple observed payloads."""

    if not first:
        return second.copy()

    if not second:
        return first.copy()

    first_type = first.get("type")
    second_type = second.get("type")

    if first_type != second_type:
        return {}

    if first_type == "object":
        first_properties = first.get("properties", {})
        second_properties = second.get("properties", {})

        merged_properties = {}

        for key in first_properties.keys() | second_properties.keys():
            if key in first_properties and key in second_properties:
                merged_properties[key] = merge_schemas(
                    first_properties[key],
                    second_properties[key],
                )
            elif key in first_properties:
                merged_properties[key] = first_properties[key]
            else:
                merged_properties[key] = second_properties[key]

        required = sorted(
            set(first.get("required", []))
            & set(second.get("required", []))
        )

        result = {
            "type": "object",
            "properties": merged_properties,
        }

        if required:
            result["required"] = required

        return result

    if first_type == "array":
        return {
            "type": "array",
            "items": merge_schemas(
                first.get("items", {}),
                second.get("items", {}),
            ),
        }

    return first.copy()


def generate_openapi_spec(
    observed_endpoints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate an OpenAPI 3.0 specification from observed traffic."""

    paths: dict[str, Any] = {}

    for endpoint in observed_endpoints:
        method = str(endpoint.get("method", "")).upper().strip()
        path = str(endpoint.get("path", "")).strip()

        if method not in HTTP_METHODS or not path:
            continue

        if not path.startswith("/"):
            path = "/" + path

        operation = paths.setdefault(path, {}).setdefault(
            method.lower(),
            {
                "responses": {
                    "200": {
                        "description": "Observed successful response",
                    }
                }
            },
        )

        request_payload = endpoint.get("request")
        if request_payload is not None:
            request_schema = infer_schema(request_payload)

            if "requestBody" not in operation:
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": request_schema,
                        }
                    },
                }
            else:
                existing = operation["requestBody"]["content"][
                    "application/json"
                ]["schema"]

                operation["requestBody"]["content"][
                    "application/json"
                ]["schema"] = merge_schemas(
                    existing,
                    request_schema,
                )

        response_payload = endpoint.get("response")
        if response_payload is not None:
            response_schema = infer_schema(response_payload)

            response = operation["responses"]["200"]
            content = response.setdefault("content", {})
            json_content = content.setdefault(
                "application/json",
                {"schema": response_schema},
            )

            if "schema" in json_content:
                json_content["schema"] = merge_schemas(
                    json_content["schema"],
                    response_schema,
                )

    return {
        "openapi": "3.0.0",
        "info": {
            "title": "API-Sentinel Dynamic API",
            "version": "1.0.0",
        },
        "paths": paths,
    }


def merge_observed_endpoint(
    observed_endpoints: list[dict[str, Any]],
    method: str,
    path: str,
    response: Any,
    request: Any = None,
) -> list[dict[str, Any]]:
    """Add one observed endpoint to the collection."""

    event = {
        "method": method.upper(),
        "path": path,
        "response": response,
    }

    if request is not None:
        event["request"] = request

    observed_endpoints.append(event)
    return observed_endpoints
