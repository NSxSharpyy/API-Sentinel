
import unittest

from src.live_discovery import LiveShadowDiscovery
from src.risk_scoring import EndpointRiskScorer


class TestLiveShadowDiscovery(unittest.TestCase):

    def setUp(self):
        # Mock official API contract
        self.official_contract = {
            "openapi": "3.0.0",
            "info": {
                "title": "Mock API",
                "version": "1.0.0",
            },
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Successful response"
                            }
                        }
                    }
                },
                "/orders": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Successful response"
                            }
                        }
                    }
                },
                "/old-api": {
                    "get": {
                        "deprecated": True,
                        "responses": {
                            "200": {
                                "description": "Deprecated response"
                            }
                        }
                    }
                },
            },
        }

        self.observed_routes = [
            "/users",
            "/orders",
            "/admin/debug",
            "/old-api",
        ]

        # Initialize discovery object for every test
        self.discovery = LiveShadowDiscovery(
            self.official_contract
        )

    def test_discovery_results_include_risk_scores(self):
        results = self.discovery.discover_with_risk_scoring([
            ("GET", "/admin/debug"),
            ("GET", "/old-api"),
            ("GET", "/orders"),
        ])

        self.assertEqual(len(results), 3)

        self.assertEqual(results[0]["risk_score"], 50)
        self.assertEqual(results[0]["risk_level"], "HIGH")

        self.assertEqual(results[1]["risk_score"], 25)
        self.assertEqual(results[1]["risk_level"], "MEDIUM")

        self.assertEqual(results[2]["risk_score"], 0)
        self.assertEqual(results[2]["risk_level"], "LOW")

    def test_discovery_risk_results_include_factors(self):
        results = self.discovery.discover_with_risk_scoring([
            ("GET", "/admin/debug"),
        ])

        factors = [
            item["factor"]
            for item in results[0]["risk_factors"]
        ]

        self.assertIn("shadow_api", factors)
        self.assertIn("sensitive_endpoint", factors)

    def test_discovery_with_custom_risk_scorer(self):
        custom_scorer = EndpointRiskScorer({
            "shadow_api": 40,
        })

        results = self.discovery.discover_with_risk_scoring(
            [("GET", "/internal")],
            scorer=custom_scorer,
        )

        self.assertEqual(results[0]["risk_score"], 40)
        self.assertEqual(results[0]["risk_level"], "HIGH")

    def test_live_discovery_classification(self):
        results = self.discovery.discover(
            self.observed_routes
        )

        self.assertEqual(len(results), 4)

        status_map = {
            item["route"]: item["status"]
            for item in results
        }

        self.assertEqual(
            status_map["/users"],
            "OFFICIAL_API",
        )

        self.assertEqual(
            status_map["/orders"],
            "OFFICIAL_API",
        )

        self.assertEqual(
            status_map["/admin/debug"],
            "SHADOW_API",
        )

        self.assertEqual(
            status_map["/old-api"],
            "ZOMBIE_API",
        )

    def test_shadow_api_detection(self):
        shadows = self.discovery.discover_shadow_apis(
            self.observed_routes
        )

        self.assertEqual(len(shadows), 1)
        self.assertEqual(shadows[0]["route"], "/admin/debug")
        self.assertEqual(shadows[0]["status"], "SHADOW_API")

    def test_zombie_api_detection(self):
        zombies = self.discovery.discover_zombie_apis(
            self.observed_routes
        )

        self.assertEqual(len(zombies), 1)
        self.assertEqual(zombies[0]["route"], "/old-api")
        self.assertEqual(zombies[0]["status"], "ZOMBIE_API")

    def test_empty_routes(self):
        results = self.discovery.discover([])

        self.assertEqual(results, [])

    def test_method_is_part_of_classification(self):
        """HTTP method must be included in runtime classification."""

        observed_routes = [
            ("GET", "/users"),
            ("DELETE", "/users"),
        ]

        results = self.discovery.discover(observed_routes)

        self.assertEqual(len(results), 2)

        self.assertEqual(results[0]["method"], "GET")
        self.assertEqual(results[0]["route"], "/users")
        self.assertEqual(results[0]["status"], "OFFICIAL_API")

        self.assertEqual(results[1]["method"], "DELETE")
        self.assertEqual(results[1]["route"], "/users")
        self.assertEqual(results[1]["status"], "SHADOW_API")

    def test_method_matching_is_case_insensitive(self):
        """HTTP methods should be normalized to uppercase."""

        results = self.discovery.discover([
            ("get", "/users"),
            ("GET", "/orders"),
        ])

        self.assertEqual(results[0]["method"], "GET")
        self.assertEqual(results[0]["status"], "OFFICIAL_API")

        self.assertEqual(results[1]["method"], "GET")
        self.assertEqual(results[1]["status"], "OFFICIAL_API")

    def test_method_aware_shadow_and_zombie_detection(self):
        """Method and path together determine Shadow/Zombie status."""

        observed_routes = [
            ("GET", "/old-api"),
            ("POST", "/old-api"),
            ("GET", "/admin/debug"),
        ]

        results = self.discovery.discover(observed_routes)

        self.assertEqual(results[0]["status"], "ZOMBIE_API")
        self.assertEqual(results[1]["status"], "SHADOW_API")
        self.assertEqual(results[2]["status"], "SHADOW_API")

    def test_invalid_contract(self):
        with self.assertRaises(ValueError):
            LiveShadowDiscovery(None)


if __name__ == "__main__":
    unittest.main()
