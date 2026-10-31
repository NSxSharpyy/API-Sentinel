
"""
OpenAPI 3.0 specification compliance validator for API-Sentinel.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft4Validator


DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "openapi-3.0-schema.json"
)


def load_openapi_schema(
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> dict[str, Any]:
    """Load and validate the official OpenAPI JSON Schema."""

    path = Path(schema_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"OpenAPI validation schema not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        schema = json.load(file)

    Draft4Validator.check_schema(schema)

    return schema


def validate_openapi_spec(
    spec: dict[str, Any],
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> dict[str, Any]:
    """
    Validate an OpenAPI document against the official OpenAPI 3.0 schema.

    Returns:
        {
            "valid": bool,
            "errors": list[str]
        }
    """

    if not isinstance(spec, dict):
        return {
            "valid": False,
            "errors": ["OpenAPI specification must be a dictionary."],
        }

    schema = load_openapi_schema(schema_path)
    validator = Draft4Validator(schema)

    validation_errors = sorted(
        validator.iter_errors(spec),
        key=lambda error: (
            list(map(str, error.absolute_path)),
            error.message,
        ),
    )

    errors = []

    for error in validation_errors:
        location = ".".join(
            str(part) for part in error.absolute_path
        ) or "<root>"

        errors.append(f"{location}: {error.message}")

    return {
        "valid": not errors,
        "errors": errors,
    }
