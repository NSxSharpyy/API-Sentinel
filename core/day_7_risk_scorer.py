from typing import Dict, Any, Set

# FIX: Define public routes to whitelist false-positive BOLA alerts
PUBLIC_ROUTES: Set[str] = {
    "/api/v1/catalog",
    "/api/v1/health",
    "/api/v1/public"
}

class Day7RiskScorer:
    def __init__(self):
        self.anomaly_weights = {
            "unusual_volume": 0.4,
            "bola_suspicion": 0.6
        }

    def calculate_score(self, request_context: Dict[str, Any]) -> float:
        path = request_context.get("path", "")
        
        # FIX: Whitelisting public paths early return bypass mapping
        if path in PUBLIC_ROUTES:
            return 0.0

        volume_anomaly = request_context.get("volume_anomaly", False)
        bola_flag = request_context.get("bola_flag", False)

        score = 0.0
        if volume_anomaly:
            score += self.anomaly_weights["unusual_volume"]
        if bola_flag:
            score += self.anomaly_weights["bola_suspicion"]

        return min(score, 1.0)
