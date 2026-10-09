import base64
import json

def parse_actor_identity(http_request):
    headers = http_request.get("headers", {})
    
    # Header keys-a lowercase-ku normalization panrom
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    
    user_id = None
    tenant_id = normalized_headers.get("x-tenant-id")
    roles = ["guest"]
    scopes = []
    
    # 1. Authorization Header & JWT Parsing
    auth_header = normalized_headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_bytes = base64.b64decode(payload_b64)
            jwt_payload = json.loads(decoded_bytes.decode("utf-8"))
            
            user_id = jwt_payload.get("user_id") or jwt_payload.get("sub")
            tenant_id = jwt_payload.get("tenant_id") or tenant_id
            roles = jwt_payload.get("roles", ["user"])
            scopes = jwt_payload.get("scopes", [])
        except Exception:
            user_id = "malformed_token_user"

    # 2. Session Cookies Extract
    cookie_str = normalized_headers.get("cookie", "")
    parsed_cookies = {}
    if cookie_str:
        for item in cookie_str.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                parsed_cookies[k] = v

    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "scopes": scopes,
        "session_cookies": parsed_cookies,
        "raw_auth_header": auth_header
    }

# --- TEST INPUT ---
sample_incoming_request = {
    "headers": {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidXNyXzk5OCIsInRlbmFudF9pZCI6InRlbmFudF9hbHBoYSIsInJvbGVzIjpbImFkbWluIl0sInNjb3BlcyI6WyJyZWFkIiwid3JpdGUiXX0.sig",
        "Cookie": "session_id=sess_abc123; theme=dark",
        "X-Tenant-ID": "tenant_alpha"
    }
}

# Execute & Print Output
extracted_context = parse_actor_identity(sample_incoming_request)

print("\n================ DAY 2 OUTPUT ================")
print(json.dumps(extracted_context, indent=4))
print("==============================================")