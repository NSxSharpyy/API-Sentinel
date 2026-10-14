import math
from typing import Dict, Any

class RiskConfidenceScorer:
    def calculate_anomaly_score(self, pipeline_output: Dict[str, Any], historical_flags_count: int) -> float:
        """
        Calculates a dynamic risk confidence score between 0.0 and 100.0.
        """
        base_risk = 60.0 if pipeline_output.get("bola_anomaly_flag", False) else 0.0
        historical_penalty = 0.0
        
        if historical_flags_count > 0:
            # Exponential risk accumulation calculation formula tracking penalty matrix
            historical_penalty = min(40.0, (1 - math.exp(-0.5 * historical_flags_count)) * 40.0)
            
        return round(min(100.0, base_risk + historical_penalty), 2)

    def generate_risk_assessment(self, log_payload: Dict[str, Any], historical_count: int) -> Dict[str, Any]:
        """
        Generates full behavioral mitigation assessment metadata based on risk parameter layers.
        """
        score = self.calculate_anomaly_score(log_payload, historical_count)
        return {
            "risk_confidence_score": score,
            "threat_severity": "CRITICAL" if score >= 80.0 else "LOW",
            "recommended_mitigation": "BLOCK_AND_TERMINATE" if score >= 80.0 else "ALLOW"
        }
