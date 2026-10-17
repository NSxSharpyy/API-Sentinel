"""Day 10 tests for deliberately injected shadow and zombie APIs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import load_app  # noqa: E402

PASSWORD = "Password123!"


@pytest.fixture(scope="module")
def clients():
    names = ("auth", "user", "order", "billing")
    return {name: load_app(f"{name}_service").test_client() for name in names}


def login_headers(clients, username):
    response = clients["auth"].post(
        "/api/v2/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    data = response.get_json()
    return {"Authorization": f"Bearer {data['token']}"}, data["user_id"]


# Shadow APIs: unauthenticated access is intentional in this lab.


def test_shadow_debug_dump_tokens_requires_no_auth(clients):
    response = clients["auth"].get("/debug/dump-tokens")
    assert response.status_code == 200
    assert "token_algorithm" in response.get_json()


def test_shadow_internal_config_requires_no_auth(clients):
    response = clients["user"].get("/internal/config")
    assert response.status_code == 200
    assert "feature_flags" in response.get_json()


def test_shadow_admin_reset_cache_requires_no_auth(clients):
    response = clients["billing"].post("/_admin/reset-cache")
    assert response.status_code == 200
    assert response.get_json()["status"] == "cache reset"


def test_shadow_endpoints_are_not_v2_routes(clients):
    for client in clients.values():
        for rule in client.application.url_map.iter_rules():
            if any(part in rule.rule for part in ("/debug/", "/internal/", "/_admin/")):
                assert "/api/v2/" not in rule.rule


# Zombie APIs: each handler independently demonstrates its weaker controls.


def test_zombie_login_status_accepts_malformed_token(clients):
    response = clients["auth"].get(
        "/api/v1/login-status",
        headers={"X-Auth-Token": "fake.notreallysigned"},
    )
    assert response.status_code == 200
    assert response.get_json()["logged_in"] is True


def test_zombie_login_status_rejects_empty_token(clients):
    response = clients["auth"].get("/api/v1/login-status")
    assert response.status_code == 200
    assert response.get_json()["logged_in"] is False


def test_zombie_user_lookup_has_no_ownership_check(clients):
    headers, requester_id = login_headers(clients, "alice")
    victim_id = requester_id + 1 if requester_id < 50 else 1

    response = clients["user"].get(
        f"/api/v1/users/{victim_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["id"] == victim_id
    assert victim_id != requester_id


def test_zombie_order_lookup_accepts_garbage_auth_header(clients):
    response = clients["order"].get(
        "/api/v1/orders/101",
        headers={"Authorization": "totally-not-a-real-token"},
    )
    assert response.status_code == 200


def test_zombie_order_lookup_rejects_empty_auth_header(clients):
    response = clients["order"].get("/api/v1/orders/101")
    assert response.status_code == 401


def test_zombie_invoice_lookup_requires_no_auth(clients):
    response = clients["billing"].get("/api/v1/invoices/1")
    assert response.status_code == 200
    assert "owner_id" in response.get_json()


def test_zombie_invoice_lookup_returns_404_for_missing_invoice(clients):
    response = clients["billing"].get("/api/v1/invoices/99999")
    assert response.status_code == 404


# Controls: the new routes must not weaken the existing v2 authentication.


def test_v2_endpoints_still_require_real_auth(clients):
    assert clients["user"].get("/api/v2/users/me").status_code == 401
    assert clients["order"].get("/api/v2/orders").status_code == 401
    assert clients["billing"].get(
        "/api/v2/billing/invoices/1"
    ).status_code == 401


def test_v2_order_responses_never_disclose_another_users_order(clients):
    headers, requester_id = login_headers(clients, "alice")

    # Probe a bounded range of seeded IDs. Existing foreign orders must not
    # be returned; nonexistent or foreign IDs may both correctly return 404.
    successful_responses = 0
    for order_id in range(1, 201):
        response = clients["order"].get(
            f"/api/v2/orders/{order_id}",
            headers=headers,
        )
        if response.status_code == 200:
            successful_responses += 1
            assert response.get_json()["user_id"] == requester_id
        else:
            assert response.status_code == 404

    assert successful_responses > 0


def test_manifest_is_separate_from_architecture_docs():
    manifest = Path(__file__).resolve().parents[2] / "docs" / "shadow_zombie_manifest.md"
    architecture = manifest.with_name("architecture.md")

    assert manifest.is_file()
    if architecture.exists():
        assert "shadow_zombie_manifest.md" not in architecture.read_text()
