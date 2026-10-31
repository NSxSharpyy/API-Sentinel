"""Day 24 tests for synthetic PII payload generation."""

import json
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "compliance" / "pii_payload_generator.py"
OUTPUT_PATH = ROOT / "data" / "pii_test_payloads.json"

sys.path.insert(0, str(GENERATOR.parent))

import pii_payload_generator as ppg


def luhn_valid(number):
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


def load_library():
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


def test_luhn_check_digit_produces_valid_card_numbers():
    prefix = "4111111111111"
    number = prefix + ppg.luhn_check_digit(prefix)
    assert luhn_valid(number)


def test_all_generated_cards_are_luhn_valid():
    cards = ppg.generate_test_credit_cards(random.Random(42), count=10)
    assert len(cards) == 10
    assert all(luhn_valid(card["value"]) for card in cards)


def test_ssns_use_invalid_900_series_area_numbers():
    ssns = ppg.generate_test_ssns(random.Random(42), count=20)
    for item in ssns:
        area = int(item["value"].split("-")[0])
        assert 900 <= area <= 999


def test_ssns_match_standard_visual_format():
    pattern = re.compile(r"^\d{3}-\d{2}-\d{4}$")
    ssns = ppg.generate_test_ssns(random.Random(42), count=10)
    assert all(pattern.fullmatch(item["value"]) for item in ssns)


def test_phone_numbers_use_fictional_nanpa_range():
    phones = ppg.generate_test_phone_numbers(random.Random(42), count=100)
    assert len({item["value"] for item in phones}) == 100
    assert all(re.fullmatch(r"\d{3}-555-01\d{2}", item["value"]) for item in phones)


def test_emails_use_reserved_test_domain():
    emails = ppg.generate_test_emails(random.Random(42), count=10)
    assert all(item["value"].endswith("@example.test") for item in emails)


def test_every_payload_has_a_unique_marker():
    library = ppg.build_library()
    markers = [
        item["marker"]
        for items in library["categories"].values()
        for item in items
    ]
    assert len(markers) == len(set(markers))
    assert len(markers) == 50


def test_every_payload_value_is_unique_within_its_category():
    library = ppg.build_library()
    for category, items in library["categories"].items():
        values = [item["value"] for item in items]
        assert len(values) == len(set(values)), category


def test_build_library_is_deterministic_across_calls():
    first = json.dumps(ppg.build_library(), sort_keys=True)
    second = json.dumps(ppg.build_library(), sort_keys=True)
    assert first == second


def test_cli_run_produces_expected_output_file():
    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert OUTPUT_PATH.exists()

    library = load_library()
    assert library["total_payloads"] == 50
    assert len(library["categories"]) == 5
    assert all(len(items) == 10 for items in library["categories"].values())


def test_no_payload_collides_with_known_seeded_customer_fields():
    library = load_library()
    values = {
        item["value"]
        for items in library["categories"].values()
        for item in items
    }
    assert "Password123!" not in values
    assert "alice.anderson1" not in values


if __name__ == "__main__":
    raise SystemExit("Run these tests with pytest.")
