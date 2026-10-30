
import unittest
from unittest import result

from src.risk_scoring import EndpointRiskScorer


class TestEndpointRiskScorer(unittest.TestCase):

    def setUp(self):
        self.scorer = EndpointRiskScorer()

    def test_official_endpoint_has_low_risk(self):
        result = self.scorer.score_endpoint({
            "method": "GET",
            "route": "/api/products",
            "status": "OFFICIAL_API",
            "authentication_required": True,
        })

        self.assertEqual(result["risk_score"], 0)
        self.assertEqual(result["risk_level"], "LOW")

    def test_shadow_api_risk(self):
        result = self.scorer.score_endpoint({
            "method": "GET",
            "route": "/api/internal",
            "status": "SHADOW_API",
        })

        self.assertEqual(result["risk_score"], 30)
        self.assertEqual(result["risk_level"], "MEDIUM")

    def test_zombie_api_risk(self):
        result = self.scorer.score_endpoint({
            "method": "GET",
            "route": "/api/legacy",
            "status": "ZOMBIE_API",
        })

        self.assertEqual(result["risk_score"], 25)
        self.assertEqual(result["risk_level"], "MEDIUM")

    def test_sensitive_endpoint_risk(self):
        result = self.scorer.score_endpoint({
            "method": "GET",
            "route": "/api/admin/users",
            "status": "OFFICIAL_API",
        })

        self.assertEqual(result["risk_score"], 20)

    def test_authentication_exposure_risk(self):
        result = self.scorer.score_endpoint({
            "method": "GET",
            "route": "/api/profile",
            "authentication_required": False,
        })

        self.assertEqual(result["risk_score"], 25)

    def test_delete_method_risk(self):
        result = self.scorer.score_endpoint({
            "method": "DELETE",
            "route": "/api/products/10",
        })

        self.assertEqual(result["risk_score"], 10)

    def test_critical_risk_classification(self):
        result = self.scorer.score_endpoint({
            "method": "DELETE",
            "route": "/api/admin/payments",
            "status": "SHADOW_API",
            "authentication_required": False,
        })

        self.assertEqual(result["risk_score"], 85)
        self.assertEqual(result["risk_level"], "CRITICAL")
        self.assertEqual(result["risk_level"], "CRITICAL")

    def test_multiple_endpoints(self):
        results = self.scorer.score_endpoints([
            {
                "method": "GET",
                "route": "/api/products",
                "status": "OFFICIAL_API",
            },
            {
                "method": "DELETE",
                "route": "/api/admin",
                "status": "SHADOW_API",
            },
        ])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["risk_level"], "LOW")
        self.assertEqual(results[1]["risk_level"], "HIGH")

    def test_custom_weights(self):
        scorer = EndpointRiskScorer({
            "shadow_api": 40,
        })

        result = scorer.score_endpoint({
            "method": "GET",
            "route": "/api/internal",
            "status": "SHADOW_API",
        })

        self.assertEqual(result["risk_score"], 40)
        self.assertEqual(result["risk_level"], "HIGH")

    def test_invalid_endpoint(self):
        with self.assertRaises(ValueError):
            self.scorer.score_endpoint({})

    def test_invalid_weight(self):
        with self.assertRaises(ValueError):
            EndpointRiskScorer({"shadow_api": -10})


if __name__ == "__main__":
    unittest.main()
