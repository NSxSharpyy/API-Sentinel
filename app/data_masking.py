"""Reusable, deterministic PII masking helpers.

This module performs pattern-based masking only. It does not guarantee
complete PII discovery and must not be treated as a replacement for
format-aware parsing or fail-closed handling of unsupported payloads.
"""
from __future__ import annotations

import ipaddress
import json
import re


MASKED = "***MASKED***"

# 13–19 digits, optionally separated by spaces or hyphens.
_CREDIT_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

_EMAIL_RE = re.compile(
    r"(?<![A-Z0-9._%+-])"
    r"[A-Z0-9.!#$%&'*+/?^_`{|}~-]+"
    r"@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+"
    r"(?![A-Z0-9.-])",
    re.IGNORECASE,
)

# Standard signed compact JWTs: base64url-encoded JSON header beginning
# with {" (normally "eyJ"), payload, and a non-empty signature.
_JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"eyJ[A-Za-z0-9_-]{5,}"
    r"\.[A-Za-z0-9_-]{2,}"
    r"\.[A-Za-z0-9_-]{8,}"
    r"(?![A-Za-z0-9_-])"
)

# Candidate phone-like values. Validation below rejects dates and IPs.
_PHONE_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"\+?(?:\(?\d)[\d(). \t:-]{5,}\d"
    r"(?![A-Za-z0-9])"
)

_DATE_RE = re.compile(
    r"(?:"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|"
    r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"
    r")"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
)


def _passes_luhn(candidate: str) -> bool:
    """Return whether a 13–19 digit candidate passes the Luhn checksum."""
    digits = re.sub(r"\D", "", candidate)

    if not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)

        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9

        checksum += digit

    return checksum % 10 == 0


def mask_credit_cards(value: str) -> str:
    """Mask card-like sequences only when their Luhn checksum is valid."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    return _CREDIT_CARD_RE.sub(
        lambda match: MASKED if _passes_luhn(match.group(0)) else match.group(0),
        value,
    )


def mask_emails(value: str) -> str:
    """Mask email-address-shaped values."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    return _EMAIL_RE.sub(MASKED, value)


def _is_date_or_ip(candidate: str) -> bool:
    """Reject common date/time and IPv4/IPv6 representations."""
    normalized = candidate.strip()

    if _DATE_RE.fullmatch(normalized):
        return True

    compact = normalized.replace(" ", "").replace("\t", "")
    try:
        ipaddress.ip_address(compact)
        return True
    except ValueError:
        return False


def _is_phone_candidate(candidate: str) -> bool:
    """Apply conservative length and formatting checks to a phone candidate."""
    digits = re.sub(r"\D", "", candidate)

    if not 7 <= len(digits) <= 15:
        return False

    if _is_date_or_ip(candidate):
        return False

    has_formatting = any(char in candidate for char in "+(). -\t:")

    # Unformatted local numbers are ambiguous. This rule deliberately
    # recognizes only plausible 10-digit national-format numbers.
    if not has_formatting:
        return len(digits) == 10 and digits[0] in "23456789"

    return True


def mask_phone_numbers(value: str) -> str:
    """Mask plausible phone numbers while rejecting common dates and IPs.

    Plain digit-only values are masked only when they contain exactly
    10 digits and begin with 2–9. Formatted values may contain 7–15 digits.
    """
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    return _PHONE_CANDIDATE_RE.sub(
        lambda match: (
            MASKED if _is_phone_candidate(match.group(0)) else match.group(0)
        ),
        value,
    )


def mask_jwt_tokens(value: str) -> str:
    """Mask standard signed compact JWT-shaped strings."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    return _JWT_RE.sub(MASKED, value)


def mask_pii(value: str) -> str:
    """Apply the four Day 25 PII masking rules to a string.

    Order matters: JWTs and card numbers are masked before phone detection,
    reducing the chance that parts of those values are treated as phone data.
    """
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    value = mask_jwt_tokens(value)
    value = mask_credit_cards(value)
    value = mask_emails(value)
    value = mask_phone_numbers(value)
    return value


# Credential fields are redacted independently of regex-detected PII.
REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "secret",
    "api_key",
    "apikey",
}

_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (?P<prefix>
        \b
        ["']?
        (?:authorization|proxy[-_]authorization|cookie|set[-_]cookie|
           password|passwd|token|access[-_]token|refresh[-_]token|
           client[-_]secret|secret|api[-_]key|apikey)
        ["']?
        \s*[:=]\s*
    )
    (?P<value>"[^"]*"|'[^']*'|[^&,\s;}\]]+)
    """
)

_BEARER_VALUE_RE = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"
)


def _normalized_sensitive_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_")


def is_sensitive_key(value: object) -> bool:
    return _normalized_sensitive_key(value) in SENSITIVE_KEYS


def sanitize_text(value: str | None) -> str | None:
    """Mask PII patterns and credential assignments in free text."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("value must be a string")

    result = mask_pii(value)
    result = _BEARER_VALUE_RE.sub("Bearer " + REDACTED, result)
    result = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: match.group("prefix") + REDACTED,
        result,
    )
    return result


def sanitize_headers(value: object) -> dict:
    """Return sanitized HTTP headers without mutating the original mapping."""
    if not isinstance(value, dict):
        return {}

    result = {}
    for key, child in value.items():
        if is_sensitive_key(key):
            result[key] = REDACTED
        elif isinstance(child, str):
            result[key] = sanitize_text(child)
        elif child is None or isinstance(child, (bool, int, float)):
            result[key] = child
        else:
            result[key] = sanitize_text(str(child))
    return result


def content_type_from_headers(headers: object) -> str | None:
    """Get Content-Type from an HTTP header mapping, case-insensitively."""
    if not isinstance(headers, dict):
        return None

    for key, value in headers.items():
        if str(key).strip().lower() == "content-type":
            return str(value)
    return None


def _sanitize_json_tree(value):
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if is_sensitive_key(key)
                else _sanitize_json_tree(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_json_tree(child) for child in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def sanitize_body(
    value: str | bytes | None,
    content_type: str | None = None,
) -> str | None:
    """Sanitize a body according to its declared media type.

    JSON and URL-encoded forms receive structured key-based redaction.
    Text formats receive pattern-based masking. Binary, multipart, unknown,
    or undecodable bodies are masked in full rather than published raw.
    """
    if value is None:
        return None

    if isinstance(value, bytes):
        if not value:
            return ""
        try:
            text_value = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return MASKED
    elif isinstance(value, str):
        text_value = value
        if not text_value:
            return ""
    else:
        raise TypeError("body must be str, bytes, or None")

    media_type = (content_type or "").split(";", 1)[0].strip().lower()

    if media_type == "application/x-www-form-urlencoded":
        from urllib.parse import parse_qsl, urlencode

        pairs = parse_qsl(text_value, keep_blank_values=True)
        sanitized_pairs = [
            (
                key,
                REDACTED if is_sensitive_key(key) else sanitize_text(child),
            )
            for key, child in pairs
        ]
        return urlencode(sanitized_pairs, doseq=True)

    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            parsed = json.loads(text_value)
        except (json.JSONDecodeError, TypeError):
            # Malformed JSON is still treated as text, with credential
            # assignment and PII patterns inspected before publication.
            return sanitize_text(text_value)
        return json.dumps(
            _sanitize_json_tree(parsed),
            separators=(",", ":"),
            ensure_ascii=False,
        )

    if (
        media_type.startswith("text/")
        or media_type in {
            "application/xml",
            "application/javascript",
            "application/x-javascript",
        }
    ):
        return sanitize_text(text_value)

    # Unknown formats, multipart, and binary media types fail closed.
    return MASKED


def sanitize_uri(value: str | None) -> str | None:
    """Sanitize a request target or URL, including query parameter values."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("URI must be a string")

    from urllib.parse import (
        parse_qsl,
        quote,
        unquote,
        urlencode,
        urlsplit,
        urlunsplit,
    )

    try:
        parsed = urlsplit(value)
    except ValueError:
        return sanitize_text(value)

    path = quote(
        sanitize_text(unquote(parsed.path)) or "",
        safe="/:@-._~!$&'()*+,;=",
    )

    if "@" in parsed.netloc:
        _, host_part = parsed.netloc.rsplit("@", 1)
        netloc = REDACTED + "@" + (sanitize_text(host_part) or "")
    else:
        netloc = sanitize_text(parsed.netloc) or ""

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    safe_query = [
        (
            key,
            REDACTED if is_sensitive_key(key) else sanitize_text(child),
        )
        for key, child in query_pairs
    ]

    fragment = sanitize_text(unquote(parsed.fragment)) or ""
    return urlunsplit((
        parsed.scheme,
        netloc,
        path,
        urlencode(safe_query, doseq=True),
        quote(fragment, safe="/:@-._~!$&'()*+,;="),
    ))
