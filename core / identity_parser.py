import jwt
from typing import Dict, Any, Optional

MOCK_SESSION_STORE: Dict[str, Dict[str, str]] = {
    "sess_harish_valid_88": {"user_id": "usr_harish77", "tenant_id": "tenant_id"},
    "sess_lead_valid_99": {"user_id": "usr_lead04", "tenant_id": "tenant_id"}
}

def parse_actor_identity(headers: Dict[str, str], public_key: str = "mock_key") -> Dict[str, Any]:
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    auth_header = normalized_headers.get("authorization")
    cookie_header = normalized_headers.get("cookie", "")

    identity_context = {"user_id": "ANONYMOUS", "tenant_id": "DEFAULT", "scopes": [], "role": "standard_user"}

    if auth_header and auth_header.lower().startswith("bearer "):
        try:
            token = auth_header.split(" ")[1]
            verified_payload = jwt.decode(
                token,
                public_key,
                algorithms=["HS256"],
                options={"verify_signature": False, "require": ["exp"]}
            )
            scopes = verified_payload.get("scopes", [])
            user_id = verified_payload.get("sub")
            tenant_id = verified_payload.get("tenant_id")
            
            # FIX: Extract privilege scopes / roles for Day 10 BFLA checks
            role = verified_payload.get("role", "standard_user")
            if "admin" in scopes:
                role = "admin"
            elif "student" in scopes:
                role = "student"

            identity_context = {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "scopes": scopes,
                "role": role
            }
        except Exception:
            return {"user_id": "MALFORMED_TOKEN", "tenant_id": "SUSPICIOUS", "scopes": [], "role": "standard_user"}

    return identity_context
