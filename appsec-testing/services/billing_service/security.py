
"""HMAC token creation, verification, and authentication for the local lab."""
import base64
import hashlib
import hmac
import json
import os
import time
from functools import wraps

from flask import g, jsonify, request

TOKEN_TTL_SECONDS = 3600


def _secret():
    secret = os.getenv("TOKEN_SECRET")
    if not secret:
        raise RuntimeError("TOKEN_SECRET must be configured")
    return secret.encode()

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(body: str) -> str:
    return _b64encode(
        hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    )


def create_token(user_id: int, ttl: int = TOKEN_TTL_SECONDS) -> str:
    claims = {"sub": user_id, "exp": int(time.time()) + ttl}
    body = _b64encode(json.dumps(claims).encode())
    return f"{body}.{_sign(body)}"


def verify_token(token: str):
    """Return an integer user ID for a valid token, otherwise None."""
    try:
        body, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(body)):
            return None

        claims = json.loads(_b64decode(body))
        user_id = claims["sub"]
        expiry = claims["exp"]

        if isinstance(user_id, bool) or not isinstance(user_id, int):
            return None
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
            return None
        if expiry <= time.time():
            return None

        return user_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def require_auth(view):
    """Require a Bearer token and set g.user_id for the request."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        scheme, _, token = request.headers.get(
            "Authorization", ""
        ).partition(" ")

        user_id = (
            verify_token(token)
            if scheme.lower() == "bearer" and token
            else None
        )

        if user_id is None:
            return jsonify(error="unauthorized"), 401

        g.user_id = user_id
        return view(*args, **kwargs)

    return wrapper
