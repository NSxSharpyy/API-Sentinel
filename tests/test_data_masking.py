import pytest

from app.data_masking import (
    MASKED,
    mask_credit_cards,
    mask_emails,
    mask_jwt_tokens,
    mask_phone_numbers,
    mask_pii,
)


JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


@pytest.mark.parametrize(
    "card",
    [
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "4222222222222",
    ],
)
def test_masks_luhn_valid_credit_cards(card):
    assert mask_credit_cards(f"payment={card}") == f"payment={MASKED}"


def test_does_not_mask_invalid_luhn_card():
    value = "card=4111 1111 1111 1112"
    assert mask_credit_cards(value) == value


def test_does_not_mask_short_numeric_sequence_as_card():
    value = "reference=1234-5678-9012"
    assert mask_credit_cards(value) == value


@pytest.mark.parametrize(
    "email",
    [
        "alice@example.com",
        "first.last+alerts@example.co.in",
        "security_user@sub.example.org",
    ],
)
def test_masks_email_addresses(email):
    assert mask_emails(f"contact {email} now") == f"contact {MASKED} now"


def test_masks_multiple_email_addresses():
    value = "alice@example.com and bob@example.org"
    assert mask_emails(value) == f"{MASKED} and {MASKED}"


@pytest.mark.parametrize(
    "phone",
    [
        "+1-202-555-0175",
        "(415) 555-2671",
        "+91 98765 43210",
        "9876543210",
    ],
)
def test_masks_phone_numbers(phone):
    assert mask_phone_numbers(f"call {phone} today") == f"call {MASKED} today"


def test_does_not_mask_date_or_ip_address_as_phone():
    value = "date=2026-11-02 host=192.168.1.10"
    assert mask_phone_numbers(value) == value


def test_does_not_mask_short_or_ambiguous_numeric_values():
    value = "port=8000 reference=123456789"
    assert mask_phone_numbers(value) == value


def test_masks_jwt():
    assert mask_jwt_tokens(f"Authorization: Bearer {JWT}") == (
        f"Authorization: Bearer {MASKED}"
    )


def test_does_not_mask_non_jwt_dotted_text():
    value = "release abcdefgh.ijklmnop.qrstuvwxyz"
    assert mask_jwt_tokens(value) == value


def test_mask_pii_applies_all_four_rules():
    value = (
        f"email=alice@example.com "
        f"phone=9876543210 "
        f"card=4111 1111 1111 1111 "
        f"token={JWT}"
    )

    result = mask_pii(value)

    assert result == (
        f"email={MASKED} "
        f"phone={MASKED} "
        f"card={MASKED} "
        f"token={MASKED}"
    )

    assert "alice@example.com" not in result
    assert "9876543210" not in result
    assert "4111 1111 1111 1111" not in result
    assert JWT not in result


def test_mask_pii_leaves_safe_text_unchanged():
    value = "GET /health HTTP/1.1 status=200"
    assert mask_pii(value) == value


@pytest.mark.parametrize(
    "function",
    [
        mask_credit_cards,
        mask_emails,
        mask_phone_numbers,
        mask_jwt_tokens,
        mask_pii,
    ],
)
def test_masking_functions_reject_non_string_input(function):
    with pytest.raises(TypeError):
        function(b"alice@example.com")


def test_preserves_email_field_name_when_masking_value():
    assert mask_emails("email=alice@example.com") == f"email={MASKED}"
