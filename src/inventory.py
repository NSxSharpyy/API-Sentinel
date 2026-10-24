import json
import re
from pathlib import Path


def normalize_api_path(path: str) -> str:
    """Normalize numeric IDs in API paths."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("API path must start with '/'.")

    segments = path.split("/")
    normalized_segments = []

    for segment in segments:
        if segment.isdigit():
            normalized_segments.append("{id}")
        else:
            normalized_segments.append(segment)

    return "/".join(normalized_segments)


def load_approved_apis(file_path: str) -> set[tuple[str, str]]:
    """Load approved API methods and normalized paths."""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Approved API inventory not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("Approved API inventory must be a JSON object.")

    approved_apis = data.get("approved_apis")

    if not isinstance(approved_apis, list):
        raise ValueError(
            "'approved_apis' must be a JSON list."
        )

    result = set()

    for api in approved_apis:
        if not isinstance(api, dict):
            raise ValueError("Each approved API must be an object.")

        method = api.get("method")
        endpoint_path = api.get("path")

        if not isinstance(method, str) or not method.strip():
            raise ValueError("Each API must have a valid method.")

        if (
            not isinstance(endpoint_path, str)
            or not endpoint_path.startswith("/")
        ):
            raise ValueError("Each API must have a valid path.")

        result.add(
            (method.upper(), normalize_api_path(endpoint_path))
        )

    return result


def find_unapproved_apis(
    discovered_apis: list[dict],
    approved_apis: set[tuple[str, str]]
) -> list[dict]:
    """Find discovered endpoints missing from the approved inventory."""
    unapproved = []

    for api in discovered_apis:
        key = (
            api["method"].upper(),
            normalize_api_path(api["path"]),
        )

        if key not in approved_apis:
            unapproved.append(api)

    return unapproved