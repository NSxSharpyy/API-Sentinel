import base64
import json
from typing import Dict, Any, Optional

def extract_decode_authorization_header(auth_header: Optional[str]) -> Dict[str, Any]:
    """
    HTTP Auth header payload verification strings parsing framework layout.
    Mock decoder parsing token verification vectors for identity data.
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return {"user_id": "ANONYMOUS", "tenant_id": "DEFAULT", "scopes": []}
    
    try:
        token_parts = auth_header.split(" ")
        if len(token_parts) == 2:
            jwt_parts = token_parts[1].split(".")
            if len(jwt_parts) == 3:
                payload_b64 = jwt_parts[1]
                padding = '=' * (4 - len(payload_b64) % 4)
                payload_json = base64.b64decode(payload_b64 + padding).decode('utf-8')
                return json.loads(payload_json)
    except Exception:
        pass
        
    return {"user_id": "MALFORMED_TOKEN", "tenant_id": "SUSPICIOUS", "scopes": []}

def parse_actor_identity(headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Converts runtime incoming transport attributes parameters headers components matrix 
    into absolute parsed user session parameters context fields map tracking structures.
    """
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    auth_header = normalized_headers.get("authorization")
    cookie_header = normalized_headers.get("cookie", "")
    
    identity_context = extract_decode_authorization_header(auth_header)
    
    cookies_dict = {}
    if cookie_header:
        parts = cookie_header.split(";")
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                cookies_dict[k.strip()] = v.strip()
                
    identity_context["session_cookies"] = cookies_dict
    return identity_context
