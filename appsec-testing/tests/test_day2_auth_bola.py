"""Day 2 tests: authentication, secure controls, and intentional BOLA."""
import sys

import pytest

from helpers import load_app

PASSWORD = "Password123!"


@pytest.fixture(scope="module")
def clients():
    names = ("auth", "user", "order", "billing")
    return {
        name: load_app(f"{name}_service").test_client()
        for name in names
    }


def login_headers(clients, username):
    response = clients["auth"].post(
        "/api/v2/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


# Authentication

def test_login_success_returns_token(clients):
    response = clients["auth"].post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.get_json()["token"]


def test_login_failures_are_indistinguishable(clients):
    wrong_password = clients["auth"].post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": "nope"},
    )
    unknown_user = clients["auth"].post(
        "/api/v2/auth/login",
        json={"username": "ghost", "password": "nope"},
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.get_json() == unknown_user.get_json()


def test_login_rejects_bad_body(clients):
    assert clients["auth"].post(
        "/api/v2/auth/login",
        json={"username": "alice"},
    ).status_code == 400
    assert clients["auth"].post(
        "/api/v2/auth/login",
        data="not json",
    ).status_code == 400


def test_verify_accepts_valid_token(clients):
    response = clients["auth"].get(
        "/api/v2/auth/verify",
        headers=login_headers(clients, "bob"),
    )
    assert response.status_code == 200
    assert response.get_json() == {"valid": True, "user_id": 2}


def test_tampered_token_is_rejected(clients):
    token = login_headers(clients, "alice")["Authorization"].split(" ")[1]
    response = clients["auth"].get(
        "/api/v2/auth/verify",
        headers={"Authorization": f"Bearer {token[:-3]}AAA"},
    )
    assert response.status_code == 401


def test_expired_token_is_rejected(clients):
    security = sys.modules["security"]
    expired_token = security.create_token(1, ttl=-10)
    response = clients["user"].get(
        "/api/v2/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


def test_garbage_authorization_headers(clients):
    for value in ["", "Bearer", "Bearer ...", "Basic abc", "Bearer a.b.c"]:
        response = clients["user"].get(
            "/api/v2/users/me",
            headers={"Authorization": value},
        )
        assert response.status_code == 401


# Secure services

def test_profile_is_own_and_hides_password_hash(clients):
    response = clients["user"].get(
        "/api/v2/users/me",
        headers=login_headers(clients, "alice"),
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["username"] == "alice"
    assert "password_hash" not in body


def test_orders_list_only_returns_own_orders(clients):
    response = clients["order"].get(
        "/api/v2/orders",
        headers=login_headers(clients, "alice"),
    )
    assert response.status_code == 200
    assert {order["id"] for order in response.get_json()["orders"]} == {101, 102}


def test_order_service_blocks_cross_user_access(clients):
    response = clients["order"].get(
        "/api/v2/orders/103",
        headers=login_headers(clients, "alice"),
    )
    assert response.status_code == 404


# Billing

def test_billing_requires_token(clients):
    assert clients["billing"].get(
        "/api/v2/billing/invoices/1"
    ).status_code == 401


def test_billing_own_invoice_works(clients):
    response = clients["billing"].get(
        "/api/v2/billing/invoices/1",
        headers=login_headers(clients, "alice"),
    )
    assert response.status_code == 200
    assert response.get_json()["owner_id"] == 1


def test_billing_list_only_returns_own_invoices(clients):
    response = clients["billing"].get(
        "/api/v2/billing/invoices",
        headers=login_headers(clients, "alice"),
    )
    assert response.status_code == 200
    assert {invoice["id"] for invoice in response.get_json()["invoices"]} == {1, 2}


def test_billing_unknown_invoice_is_404(clients):
    response = clients["billing"].get(
        "/api/v2/billing/invoices/9999",
        headers=login_headers(clients, "alice"),
    )
    assert response.status_code == 404


def test_billing_bola_vulnerability_is_present(clients):
    """Lab assertion: Alice can access Bob's invoice by changing its ID."""
    response = clients["billing"].get(
        "/api/v2/billing/invoices/3",
        headers=login_headers(clients, "alice"),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["owner_id"] == 2
    assert body["card_last4"] == "1881"
