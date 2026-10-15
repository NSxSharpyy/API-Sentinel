import json
import time

class TelemetryFeatureExtractor:
    """
    Day 8 Task: Dynamic Feature Extraction & Telemetry Engine
    Extracts security indicators (IP rotation, request frequency, dynamic context)
    from request payloads for threat detection.
    """
    def __init__(self):
        # In-memory session tracking
        self.user_history = {}

    def extract_features(self, request_payload):
        actor_context = request_payload.get("actor_context", {})
        user_id = actor_context.get("user_id", "anonymous")
        ip_address = request_payload.get("ip_address", "0.0.0.0")
        user_agent = request_payload.get("user_agent", "Unknown")
        timestamp = request_payload.get("timestamp", time.time())
        
        # Session metrics look-up
        history = self.user_history.get(user_id, {"last_ip": ip_address, "ip_changes": 0, "request_count": 0})
        
        # Feature 1: IP Rotation Check
        ip_rotated = False
        if history["last_ip"] != ip_address:
            ip_rotated = True
            history["ip_changes"] += 1
            
        history["request_count"] += 1
        history["last_ip"] = ip_address
        self.user_history[user_id] = history

        # Extracted Features Telemetry Payload
        return {
            "user_id": user_id,
            "roles": actor_context.get("roles", []),
            "target_object_owner_id": request_payload.get("target_object_owner_id"),
            "request_path": request_payload.get("path", ""),
            "is_sensitive_route": request_payload.get("is_sensitive", False),
            "telemetry_indicators": {
                "ip_address": ip_address,
                "ip_rotated": ip_rotated,
                "total_ip_changes": history["ip_changes"],
                "total_user_requests": history["request_count"],
                "user_agent": user_agent
            }
        }


if __name__ == "__main__":
    extractor = TelemetryFeatureExtractor()

    print("\n================ DAY 8 TELEMETRY EXTRACTION TEST ================")

    # Test 1: Baseline Extraction
    req1 = {
        "actor_context": {"user_id": "usr_707", "roles": ["user"]},
        "target_object_owner_id": "usr_707",
        "path": "/api/v1/profile/view",
        "is_sensitive": False,
        "ip_address": "192.168.1.50",
        "user_agent": "Mozilla/5.0"
    }
    feat1 = extractor.extract_features(req1)
    print("\n[REQUEST 1 - Baseline Extraction]:")
    print(json.dumps(feat1, indent=4))

    # Test 2: IP Rotation Anomaly
    req2 = {
        "actor_context": {"user_id": "usr_707", "roles": ["user"]},
        "target_object_owner_id": "usr_888_victim",
        "path": "/api/v1/billing/update",
        "is_sensitive": True,
        "ip_address": "10.0.0.99",
        "user_agent": "Python-requests/2.28"
    }
    feat2 = extractor.extract_features(req2)
    print("\n[REQUEST 2 - IP Shift Detected]:")
    print(json.dumps(feat2, indent=4))

    print("==================================================================")
