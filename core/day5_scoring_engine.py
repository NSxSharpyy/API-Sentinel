import json

def calculate_anomaly_score(actor_context, target_object_owner_id, request_path, is_sensitive_route=False):
    """
    Day 5 Task: Calculate anomaly score using ownership discrepancies,
    session roles, and request paths.
    """
    score = 0.0
    reasons = []

    user_id = actor_context.get("user_id")
    roles = actor_context.get("roles", [])

    # Factor 1: Ownership Discrepancy Check (Base Score: 0.5)
    if user_id != target_object_owner_id:
        score += 0.5
        reasons.append("Ownership mismatch: User does not own the requested object")

    # Factor 2: Role & Privilege Risk (Score Weight: +0.2)
    if "guest" in roles or "anonymous" in roles:
        score += 0.2
        reasons.append("High-risk role: Request initiated by unverified/guest role")
    elif "admin" in roles:
        # Admin discount
        score -= 0.3
        reasons.append("Low-risk role: Request initiated by admin")

    # Factor 3: High-Risk Action Path / Sensitive Route (Score Weight: +0.3)
    if is_sensitive_route or any(keyword in request_path.lower() for keyword in ["/delete", "/update", "/billing", "/export"]):
        score += 0.3
        reasons.append("Sensitive path action: High impact route targeted")

    # Cap the final score between 0.0 and 1.0
    final_score = round(max(0.0, min(1.0, score)), 2)

    # Risk level categorization
    if final_score >= 0.7:
        risk_level = "CRITICAL (BOLA Attack Likely)"
    elif final_score >= 0.4:
        risk_level = "MEDIUM (Suspicious Activity)"
    else:
        risk_level = "LOW (Legitimate Request)"

    return {
        "user_id": user_id,
        "request_path": request_path,
        "confidence_score": final_score,
        "risk_level": risk_level,
        "scoring_factors": reasons
    }


# --- TEST CASES FOR DAY 5 ---
print("\n================ DAY 5 ANOMALY SCORING ENGINE ================")

# Test Case 1: Regular user accessing another user's sensitive billing path (BOLA Attack)
suspicious_context = {
    "user_id": "usr_998",
    "roles": ["user"]
}

result_attack = calculate_anomaly_score(
    actor_context=suspicious_context,
    target_object_owner_id="usr_111_victim",
    request_path="/api/v1/billing/update",
    is_sensitive_route=True
)
print("\n[TEST 1 - High Risk / BOLA Attack]:")
print(json.dumps(result_attack, indent=4))

# Test Case 2: Normal user accessing their own profile (Safe)
result_safe = calculate_anomaly_score(
    actor_context=suspicious_context,
    target_object_owner_id="usr_998",
    request_path="/api/v1/profile/view",
    is_sensitive_route=False
)
print("\n[TEST 2 - Legitimate Access]:")
print(json.dumps(result_safe, indent=4))

print("==============================================================")
