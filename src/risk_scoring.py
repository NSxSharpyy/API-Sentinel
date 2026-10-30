
"""
Endpoint Risk Scoring Engine for API-Sentinel.

Calculates configurable security risk scores for discovered API endpoints.
"""

from typing import Any


class EndpointRiskScorer:
    """Assign risk scores and severity levels to API endpoints."""

    DEFAULT_WEIGHTS = {
        "shadow_api": 30,
        "zombie_api": 25,
        "sensitive_endpoint": 20,
        "authentication_exposure": 25,
        "high_risk_method": 10,
    }

    SENSITIVE_KEYWORDS = {
        "admin",
        "auth",
        "authentication",
        "payment",
        "payments",
        "password",
        "token",
        "credential",
        "users",
        "account",
    }

    HIGH_RISK_METHODS = {"DELETE"}

    def __init__(self, weights: dict[str, int] | None = None):
        self.weights = dict(self.DEFAULT_WEIGHTS)

        if weights:
            for factor, value in weights.items():
                if factor not in self.weights:
                    raise ValueError(f"Unknown risk factor: {factor}")

                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError("Risk weights must be integers")

                if value < 0:
                    raise ValueError("Risk weights cannot be negative")

                self.weights[factor] = value

    @staticmethod
    def _get_risk_level(score: int) -> str:
        if score >= 70:
            return "CRITICAL"
        if score >= 40:
            return "HIGH"
        if score >= 20:
            return "MEDIUM"
        return "LOW"

    def score_endpoint(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """Calculate the risk score for one discovered endpoint."""

        if not isinstance(endpoint, dict):
            raise ValueError("Endpoint must be a dictionary")

        route = endpoint.get("route", endpoint.get("path", ""))
        method = str(endpoint.get("method", "")).upper()
        status = str(endpoint.get("status", "")).upper()

        if not isinstance(route, str) or not route.strip():
            raise ValueError("Endpoint must contain a valid route")

        factors = {
            "shadow_api": status == "SHADOW_API",
            "zombie_api": status == "ZOMBIE_API",
            "sensitive_endpoint": any(
                keyword in route.lower()
                for keyword in self.SENSITIVE_KEYWORDS
            ),
            "authentication_exposure": (
                endpoint.get("authentication_required") is False
            ),
            "high_risk_method": method in self.HIGH_RISK_METHODS,
        }

        reasons = []
        score = 0

        for factor, triggered in factors.items():
            if triggered:
                points = self.weights[factor]
                score += points
                reasons.append({
                    "factor": factor,
                    "points": points,
                })

        score = min(score, 100)

        return {
            **endpoint,
            "risk_score": score,
            "risk_level": self._get_risk_level(score),
            "risk_factors": reasons,
        }

    def score_endpoints(
        self,
        endpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Calculate risk scores for multiple endpoints."""

        if not isinstance(endpoints, list):
            raise ValueError("Endpoints must be provided as a list")

        return [
            self.score_endpoint(endpoint)
            for endpoint in endpoints
        ]
