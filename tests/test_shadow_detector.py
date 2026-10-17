import unittest

from src.route_matcher import RouteMatcher
from src.shadow_detector import ShadowAPIDetector


class TestShadowAPIDetector(unittest.TestCase):

    def setUp(self):
        contracts = [
            {
                "method": "GET",
                "path": "/api/v1/users",
            },
            {
                "method": "GET",
                "path": "/api/v1/orders/{id}",
            },
        ]

        self.matcher = RouteMatcher(contracts)
        self.detector = ShadowAPIDetector(self.matcher)

    def test_declared_endpoint_is_not_shadow(self):
        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/users",
            }
        ]

        findings = self.detector.detect(observed_routes)

        self.assertEqual(findings, [])

    def test_undocumented_endpoint_is_shadow(self):
        observed_routes = [
            {
                "method": "POST",
                "route": "/api/v1/internal/debug",
            }
        ]

        findings = self.detector.detect(observed_routes)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "shadow")
        self.assertEqual(findings[0]["finding"], "Shadow API")

    def test_mixed_declared_and_shadow_routes(self):
        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/users",
            },
            {
                "method": "GET",
                "route": "/api/v1/orders/123",
            },
            {
                "method": "POST",
                "route": "/api/v1/internal/debug",
            },
        ]

        findings = self.detector.detect(observed_routes)

        self.assertEqual(len(findings), 1)

        routes = {finding["route"] for finding in findings}

        self.assertIn("/api/v1/internal/debug", routes)

    def test_method_mismatch_is_shadow(self):
        observed_routes = [
            {
                "method": "POST",
                "route": "/api/v1/users",
            }
        ]

        findings = self.detector.detect(observed_routes)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "shadow")

    def test_empty_observed_routes(self):
        findings = self.detector.detect([])

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()