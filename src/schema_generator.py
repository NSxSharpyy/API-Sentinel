"""
Dynamic OpenAPI 3.0 schema generator for API-Sentinel.

Builds an OpenAPI schema from observed JSON request/response payloads.
"""

from __future__ import annotations

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


def infer_schema(value: Any) -> dict[str, Any]:
    """Infer a basic OpenAPI-compatible schema from a Python value."""

    if value is None:
        return {"nullable": True}

    if isinstance(value, bool):
        return {"type": "boolean"}

    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}

    if isinstance(value, float):
        return {"type": "number"}

    if isinstance(value, str):
        return {"type": "string"}

    if isinstance(value, list):
        if not value:
            return {"type": "array"}

        item_schemas = [infer_schema(item) for item in value]

        first_schema = item_schemas[0]

        if all(schema == first_schema for schema in item_schemas):
            return {
                "type": "array",
                "items": first_schema,
            }

        return {
            "type": "array",
            "items": {},
        }

    if isinstance(value, dict):
        properties = {}
        required = []

        for key, item in value.items():
            properties[key] = infer_schema(item)
            required.append(key)

        schema = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    return {}


def generate_openapi_spec(
    observed_endpoints: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generate an OpenAPI 3.0 specification from observed API traffic.

    Expected endpoint format:

    {
        "method": "GET",
        "path": "/api/v1/users",
        "response": {
            "id": 1,
            "name": "Shirish"
        }
    }
    """

    paths: dict[str, Any] = {}

    for endpoint in observed_endpoints:
        method = str(endpoint.get("method", "")).upper().strip()
        path = str(endpoint.get("path", "")).strip()

        if method not in HTTP_METHODS:
            continue

        if not path.startswith("/"):
            path = "/" + path

        response_payload = endpoint.get("response")

        if path not in paths:
            paths[path] = {}

        operation = {
            "responses": {
                "200": {
                    "description": "Observed successful response",
                }
            }
        }

        if response_payload is not None:
            operation["responses"]["200"]["content"] = {
                "application/json": {
                    "schema": infer_schema(response_payload)
                }
            }

        paths[path][method.lower()] = operation

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
) -> list[dict[str, Any]]:
    """Add one observed endpoint to the collection."""

    observed_endpoints.append(
        {
            "method": method.upper(),
            "path": path,
            "response": response,
        }
    )

    return observed_endpoints


if __name__ == "__main__":
    sample_events = [
        {
            "method": "GET",
            "path": "/api/v1/users",
            "response": {
                "id": 1,
                "name": "Shirish",
                "active": True,
            },
        },
        {
            "method": "GET",
            "path": "/api/v1/orders/123",
            "response": {
                "id": 123,
                "amount": 499.50,
            },
        },
    ]

    import json

    generated_spec = generate_openapi_spec(sample_events)

    print(json.dumps(generated_spec, indent=2))