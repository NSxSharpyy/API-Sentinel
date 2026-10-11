
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


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5002")),
        debug=False,
    )
