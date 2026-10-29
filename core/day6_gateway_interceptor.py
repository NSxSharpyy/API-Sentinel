import json

def calculate_anomaly_score(actor_context, target_object_owner_id, request_path, is_sensitive_route=False):
    score = 0.0
    reasons = []
    user_id = actor_context.get("user_id")
    roles = actor_context.get("roles", [])

    if user_id != target_object_owner_id:
        score += 0.5
        reasons.append("Ownership mismatch: User does not own requested object")

    if "guest" in roles or "anonymous" in roles:
        score += 0.2
        reasons.append("High-risk role")
    elif "admin" in roles:
        score -= 0.3

    if is_sensitive_route or any(k in request_path.lower() for k in ["/delete", "/update", "/billing"]):
        score += 0.3
        reasons.append("Sensitive path action")

    final_score = round(max(0.0, min(1.0, score)), 2)
    risk_level = "CRITICAL (BOLA Attack Likely)" if final_score >= 0.7 else ("MEDIUM" if final_score >= 0.4 else "LOW")

    return {"user_id": user_id, "confidence_score": final_score, "risk_level": risk_level, "factors": reasons}

class APIGatewayInterceptor:
    def __init__(self, risk_threshold=0.7):
        self.risk_threshold = risk_threshold

    def process_request(self, http_request):
        scoring_result = calculate_anomaly_score(
            actor_context=http_request.get("actor_context", {}),
            target_object_owner_id=http_request.get("target_object_owner_id"),
            request_path=http_request.get("path", ""),
            is_sensitive_route=http_request.get("is_sensitive", False)
        )
        if scoring_result["confidence_score"] >= self.risk_threshold:
            return {"status": 403, "action": "BLOCKED", "telemetry": scoring_result}
        return {"status": 200, "action": "ALLOWED", "telemetry": scoring_result}

if __name__ == "__main__":
    interceptor = APIGatewayInterceptor(risk_threshold=0.7)

    attack = interceptor.process_request({
        "actor_context": {"user_id": "usr_998", "roles": ["user"]},
        "target_object_owner_id": "usr_111_victim",
        "path": "/api/v1/billing/update",
        "is_sensitive": True
    })

    legit = interceptor.process_request({
        "actor_context": {"user_id": "usr_998", "roles": ["user"]},
        "target_object_owner_id": "usr_998",
        "path": "/api/v1/profile/view",
        "is_sensitive": False
    })

    print("\n=== DAY 6 INTERCEPTOR TEST ===")
    print("[TEST 1 - BOLA Attack]:\n", json.dumps(attack, indent=4))
    print("\n[TEST 2 - Legit Request]:\n", json.dumps(legit, indent=4))
