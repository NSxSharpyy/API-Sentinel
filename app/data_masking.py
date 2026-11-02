"""Reusable, deterministic PII masking helpers.

This module performs pattern-based masking only. It does not guarantee
complete PII discovery and must not be treated as a replacement for
format-aware parsing or fail-closed handling of unsupported payloads.
"""
from __future__ import annotations

import ipaddress
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
