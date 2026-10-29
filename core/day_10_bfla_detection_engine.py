# core/day_10_bfla_detection_engine.py
"""
Day 10 / Issue 8: Canonical Role Format and Boundary-Aware BFLA Engine.
"""
import json

class CanonicalBFLAEngine:
    def __init__(self):
        # Strict administrative management routes mapping limits
        self.protected_admin_routes = [
            "/api/v1/admin/management",
            "/api/v1/admin/users/delete"
        ]

    def verify_bfla_clearance(self, incoming_role: str, request_path: str) -> dict:
        """
        Fix Issue 8: Enforce canonical role normalization and boundary-aware route checks
        to prevent accidental privilege grants via custom substring inputs.
        """
        if not incoming_role or not request_path:
            return {"access_authorized": False, "alert_status": "MALFORMED_CONTEXT_REJECTED"}

        # Action A: Canonical normalization of user roles to clear mismatches
        canonical_role = incoming_role.strip().upper()
        normalized_route = request_path.strip().rstrip("/")

        # Action B: Safe boundary-aware administrative endpoint checking
        is_admin_path = False
        for admin_route in self.protected_admin_routes:
            if normalized_route == admin_route or normalized_route.startswith(admin_route + "/"):
                is_admin_path = True
                break

        # Access Restriction Guard Check
        if is_admin_path and canonical_role != "ADMIN":
            return {
                "access_authorized": False,
                "normalized_role_used": canonical_role,
                "alert_status": "UNAUTHORIZED_ADMINISTRATIVE_ACCESS_DENIED_BFLA"
            }

        return {
            "access_authorized": True,
            "normalized_role_used": canonical_role,
            "alert_status": "ACCESS_REQUEST_APPROVED"
        }

if __name__ == "__main__":
    engine = CanonicalBFLAEngine()
    print("Testing clean standard user on admin route:", json.dumps(engine.verify_bfla_clearance("standard_user", "/api/v1/admin/management"), indent=4))
