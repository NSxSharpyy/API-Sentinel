import re
from urllib.parse import urlsplit


# Supported HTTP methods are kept here for consistency
# with the rest of the API-Sentinel project.
HTTP_METHODS = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
    "TRACE",
}


# UUID v1-v5 style identifier.
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


# Pure numeric identifiers.
NUMERIC_PATTERN = re.compile(
    r"^\d+$"
)


def normalize_route(url: str) -> str:
    """
    Normalize a runtime URL path into an API route template.

    Dynamic identifiers are normalized only when there is strong
    evidence that the segment is an identifier.

    Supported dynamic identifiers:
        /users/123
        /users/456789
        /users/550e8400-e29b-41d4-a716-446655440000

    Static route names are preserved:
        /api/documentation
        /api/administration
        /api/user-management
        /api/v1/healthcheck

    Query strings and fragments are removed.
    Trailing slashes are removed except for the root route.
    """

    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")

    # urlsplit allows us to safely handle:
    #
    # /users/123
    # https://example.com/users/123?active=true
    # /users/123#profile
    #
    # In all cases we only care about the path.
    path = urlsplit(url.strip()).path

    if not path.startswith("/"):
        path = "/" + path

    # Remove trailing slash except for "/".
    if path != "/":
        path = path.rstrip("/")

    if not path:
        return "/"

    segments = path.split("/")

    normalized_segments = []

    for segment in segments:
        # Preserve empty segments created by the leading slash.
        if not segment:
            normalized_segments.append("")
            continue

        # ---------------------------------------------------------
        # Dynamic identifier #1: numeric ID
        # ---------------------------------------------------------
        #
        # Examples:
        #   /users/123      -> /users/{id}
        #   /orders/98765   -> /orders/{id}
        #
        # This is a strong signal that the segment is an ID.
        if NUMERIC_PATTERN.fullmatch(segment):
            normalized_segments.append("{id}")
            continue

        # ---------------------------------------------------------
        # Dynamic identifier #2: UUID
        # ---------------------------------------------------------
        #
        # Example:
        #   /users/550e8400-e29b-41d4-a716-446655440000
        #
        # UUID format is specific enough that we can safely
        # classify it as an identifier.
        if UUID_PATTERN.fullmatch(segment):
            normalized_segments.append("{id}")
            continue

        # ---------------------------------------------------------
        # Everything else remains unchanged.
        # ---------------------------------------------------------
        #
        # IMPORTANT:
        #
        # We intentionally removed the previous "10+ character
        # alphanumeric => {id}" rule.
        #
        # Therefore:
        #
        # /documentation
        # /administration
        # /user-management
        #
        # remain static route segments.
        normalized_segments.append(segment)

    normalized_path = "/".join(normalized_segments)

    return normalized_path or "/"


def normalize_method(method: str) -> str:
    """
    Normalize an HTTP method.

    Example:
        get     -> GET
        Post    -> POST
        DELETE  -> DELETE
    """

    if not isinstance(method, str) or not method.strip():
        raise ValueError("HTTP method must be a non-empty string.")

    normalized_method = method.strip().upper()

    if normalized_method not in HTTP_METHODS:
        raise ValueError(
            f"Unsupported HTTP method: {normalized_method}"
        )

    return normalized_method