import unittest

from src.route_matcher import RouteMatcher
from src.zombie_detector import ZombieAPIDetector


class TestZombieIntegration(unittest.TestCase):

    def test_declared_deprecated_route_becomes_zombie(self):

        official_contract = {
            "paths": {
                "/api/v1/users": {
                    "get": {
                        "deprecated": False
                    }
                },
                "/api/v1/old-users": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        declared_contracts = [
            {
                "method": "GET",
                "path": "/api/v1/users"
            },
            {
                "method": "GET",
                "path": "/api/v1/old-users"
            }
        ]

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/users"
            },
            {
                "method": "GET",
                "route": "/api/v1/old-users"
            }
        ]

        matcher = RouteMatcher(declared_contracts)

        matched_routes = matcher.match_observed_routes(
            observed_routes
        )

        detector = ZombieAPIDetector(
            official_contract
        )

        findings = detector.analyze(
            matched_routes
        )

        self.assertEqual(len(findings), 1)

        self.assertEqual(
            findings[0]["method"],
            "GET"
        )

        self.assertEqual(
            findings[0]["route"],
            "/api/v1/old-users"
        )

        self.assertEqual(
            findings[0]["status"],
            "ZOMBIE_API"
        )


if __name__ == "__main__":
    unittest.main()