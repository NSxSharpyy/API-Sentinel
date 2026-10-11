
"""MOCK Auth Service: login and token verification."""
import os

from flask import g, jsonify, request
from werkzeug.security import check_password_hash

from mock_data import find_user_by_username
from security import create_token, require_auth
from service_base import create_service

app, logger = create_service("auth-service")


@app.post("/api/v2/auth/login")
def login():
    body = request.get_json(silent=True)

    if not isinstance(body, dict) or not body.get("username") or not body.get("password"):
        return jsonify(error="bad_request", detail="username and password required"), 400

    username = str(body["username"])
    user = find_user_by_username(username)

    if user is None or not check_password_hash(
        user["password_hash"], str(body["password"])
    ):
        logger.warning(
            "login failed",
            extra={"fields": {"username": username[:64]}},
        )
        return jsonify(error="invalid_credentials"), 401

    return jsonify(
        token=create_token(user["id"]),
        user_id=user["id"],
        token_type="Bearer",
    )


@app.get("/api/v2/auth/verify")
@require_auth
def verify():
    return jsonify(valid=True, user_id=g.user_id)


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5001")),
        debug=False,
    )
