
"""MOCK User Management Service."""
import os

from flask import g, jsonify

from mock_data import get_user, public_user
from security import require_auth
from service_base import create_service

app, logger = create_service("user-service")


@app.get("/api/v2/users/me")
@require_auth
def get_profile():
    user = get_user(g.user_id)
    if user is None:
        return jsonify(error="not_found"), 404
    return jsonify(public_user(user))



# Day 10 SHADOW API: unauthenticated internal configuration disclosure.
@app.get("/internal/config")
def internal_config():
    logger.warning(
        "SHADOW API accessed",
        extra={"fields": {"endpoint": "/internal/config"}},
    )
    return jsonify(
        warning="internal debug endpoint - not for external use",
        environment="lab-test",
        feature_flags={
            "new_profile_ui": False,
            "legacy_v1_enabled": True,
        },
    )


# Day 10 ZOMBIE API: legacy user lookup lacks an ownership check.
@app.get("/api/v1/users/<int:user_id>")
@require_auth
def v1_get_user(user_id):
    logger.warning(
        "ZOMBIE API accessed",
        extra={"fields": {
            "endpoint": "/api/v1/users/<id>",
            "requester_id": g.user_id,
            "target_id": user_id,
        }},
    )
    user = get_user(user_id)
    if user is None:
        return jsonify(error="not_found"), 404
    return jsonify(public_user(user))


# Assignment-specific Day 16 ZOMBIE API: deprecated export endpoint.
# LOCAL LAB ONLY; returns synthetic data and exports no real user records.
@app.get("/api/v0/users/export")
def zombie_export_users():
    logger.warning(
        "ZOMBIE API accessed",
        extra={"fields": {"endpoint": "/api/v0/users/export"}},
    )
    return jsonify(status="deprecated", data="synthetic-lab-data")


# Assignment-specific Day 16 SHADOW API: undocumented debug metrics.
# LOCAL LAB ONLY; values are synthetic and disclose no host metrics.
@app.get("/api/v1/debug/metrics")
def shadow_debug_metrics():
    logger.warning(
        "SHADOW API accessed",
        extra={"fields": {"endpoint": "/api/v1/debug/metrics"}},
    )
    return jsonify(cpu="42%", mem="1GB")


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5002")),
        debug=False,
    )
