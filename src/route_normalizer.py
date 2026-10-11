import re
from urllib.parse import urlsplit


def normalize_route(url: str) -> str:
    """Convert dynamic URL paths into normalized route templates."""

    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")

    path = urlsplit(url.strip()).path

    if not path.startswith("/"):
        path = "/" + path

    # Remove trailing slashes, except for the root route.
    if path != "/":
        path = path.rstrip("/")

    segments = path.split("/")

    normalized_segments = []

    for segment in segments:
        if not segment:
            normalized_segments.append("")
        elif segment.isdigit():
            normalized_segments.append("{id}")
        else:
            normalized_segments.append(segment)

    normalized_path = "/".join(normalized_segments)

    # Keep the root route as "/".
    return normalized_path or "/"