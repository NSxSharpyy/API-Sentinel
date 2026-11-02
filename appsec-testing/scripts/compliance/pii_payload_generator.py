#!/usr/bin/env python3
"""Generate deterministic, synthetic PII-shaped test payloads for Day 25.

No live services, real credentials, or personal information are used.
"""

import base64
import json
import random
from pathlib import Path

SEED = 2024
ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "pii_test_payloads.json"

# Published payment-processor test PANs. These are fixed test values,
# not randomly fabricated account numbers.
TEST_CARDS = [
    ("visa_test", "4242424242424242"),
    ("visa_test", "4000056655665556"),
    ("visa_test", "4000000000009995"),
    ("visa_test", "4000000000009987"),
    ("visa_test", "4000000000009979"),
    ("visa_test", "4000000000000069"),
    ("visa_test", "4000000000000127"),
    ("mastercard_test", "5555555555554444"),
    ("mastercard_test", "5200828282828210"),
    ("amex_test", "378282246310005"),
]


def luhn_check_digit(number_without_check_digit: str) -> str:
    """Return the Luhn check digit for a numeric prefix."""
    digits = [int(char) for char in number_without_check_digit]
    digits.reverse()

    total = 0
    for index, digit in enumerate(digits):
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit

    return str((-total) % 10)


def luhn_is_valid(number: str) -> bool:
    """Independently structured Luhn validation helper."""
    digits = [int(char) for char in number]
    digits.reverse()

    total = 0
    for index, digit in enumerate(digits):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit

    return total % 10 == 0


def generate_test_credit_cards(rng, count=10):
    del rng  # Fixed published test values keep the fixture recognizable.

    if not 0 <= count <= len(TEST_CARDS):
        raise ValueError(f"count must be between 0 and {len(TEST_CARDS)}")

    cards = []
    for index, (network, number) in enumerate(TEST_CARDS[:count]):
        if not luhn_is_valid(number):
            raise ValueError(f"Configured test card failed Luhn validation: {number}")

        cards.append({
            "marker": f"PII-TEST-CARD-{index:03d}",
            "value": number,
            "network": network,
            "format": "luhn-valid-processor-test-number",
            "last4": number[-4:],
        })

    return cards


def generate_test_ssns(rng, count=10):
    """Generate SSN-shaped values with invalid SSA area numbers (900-999).

    The 900-series is not a valid SSN area range. These values are
    deliberately unissuable, not an SSA-designated testing allocation.
    """
    ssns = []
    seen = set()

    while len(ssns) < count:
        area = rng.randint(900, 999)
        group = rng.randint(1, 99)
        serial = rng.randint(1, 9999)
        value = f"{area:03d}-{group:02d}-{serial:04d}"

        if value in seen:
            continue

        seen.add(value)
        index = len(ssns)
        ssns.append({
            "marker": f"PII-TEST-SSN-{index:03d}",
            "value": value,
            "format": "###-##-####",
            "safety_basis": "invalid-ssa-area-900-series",
        })

    return ssns


def generate_test_bearer_tokens(rng, count=10):
    """Generate opaque, high-entropy bearer-token-shaped test strings."""
    tokens = []

    for index in range(count):
        body = bytes(rng.getrandbits(8) for _ in range(32))
        signature = bytes(rng.getrandbits(8) for _ in range(16))

        body_part = base64.urlsafe_b64encode(body).decode().rstrip("=")
        signature_part = base64.urlsafe_b64encode(signature).decode().rstrip("=")

        tokens.append({
            "marker": f"PII-TEST-TOKEN-{index:03d}",
            "value": f"{body_part}.{signature_part}",
            "format": "opaque-bearer-shaped-test-token",
            "credential_status": "synthetic-not-valid",
        })

    return tokens


def generate_test_emails(rng, count=10):
    del rng

    return [
        {
            "marker": f"PII-TEST-EMAIL-{index:03d}",
            "value": f"pii.test.user{index:03d}@example.test",
            "format": "reserved-test-domain",
        }
        for index in range(count)
    ]


def generate_test_phone_numbers(rng, count=10):
    del rng

    if not 0 <= count <= 100:
        raise ValueError("count must be between 0 and 100")

    return [
        {
            "marker": f"PII-TEST-PHONE-{index:03d}",
            "value": f"202-555-01{index:02d}",
            "format": "nanpa-fictional-555-01xx",
        }
        for index in range(count)
    ]


def build_library():
    rng = random.Random(SEED)

    categories = {
        "credit_cards": generate_test_credit_cards(rng),
        "ssns": generate_test_ssns(rng),
        "bearer_tokens": generate_test_bearer_tokens(rng),
        "emails": generate_test_emails(rng),
        "phone_numbers": generate_test_phone_numbers(rng),
    }

    return {
        "schema_version": 1,
        "seed": SEED,
        "safety_note": (
            "Synthetic test values only. Payment cards are published "
            "processor test numbers; SSN-shaped values use invalid 900-series "
            "area numbers; tokens are random and nonfunctional; emails use "
            "example.test; phone numbers use the fictional 555-0100–0199 range."
        ),
        "categories": categories,
        "total_payloads": sum(len(items) for items in categories.values()),
    }


def main():
    library = build_library()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_PATH.write_text(
        json.dumps(library, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"Generated {library['total_payloads']} test payloads "
        f"across {len(library['categories'])} categories:"
    )
    for category, items in library["categories"].items():
        print(f"  {category}: {len(items)}")

    print(f"\nSaved: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
