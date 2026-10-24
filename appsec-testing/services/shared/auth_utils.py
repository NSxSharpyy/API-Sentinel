"""HMAC-signed tokens for the local API-Sentinel training lab."""
import base64
import hashlib
import hmac
import json
import os
import time


def _encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret():
    secret = os.getenv("TOKEN_SECRET")
    if not secret:
        raise RuntimeError("TOKEN_SECRET must be configured")
    return secret.encode()

def issue_token(user_id, ttl=None):
    ttl = int(ttl or os.getenv("TOKEN_TTL_SECONDS", "3600"))
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _encode(
        hmac.new(_secret(), encoded.encode(), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def verify_token(token):
    try:
        encoded, signature = token.split(".", 1)
        expected = _encode(
            hmac.new(_secret(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None

        payload = json.loads(_decode(encoded))
        if not isinstance(payload.get("sub"), str):
            return None
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None

        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
