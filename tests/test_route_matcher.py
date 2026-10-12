import unittest

from src.route_matcher import RouteMatcher


class TestRouteMatcher(unittest.TestCase):

    def setUp(self):
        contracts = [
            {"method": "GET", "path": "/api/v1/orders/{id}"},
            {"method": "POST", "path": "/api/v1/orders"},
            {"method": "GET", "path": "/api/v1/users/{id}"},
        ]
        self.matcher = RouteMatcher(contracts)

    def test_matches_declared_route(self):
        result = self.matcher.match_route(
            "GET", "/api/v1/orders/{id}"
        )

        self.assertTrue(result["declared"])
        self.assertEqual(result["status"], "declared")

    def test_identifies_undocumented_route(self):
        result = self.matcher.match_route(
            "DELETE", "/api/v1/orders/{id}"
        )

        self.assertFalse(result["declared"])
        self.assertEqual(
            result["status"], "potentially_undocumented"
        )

    def test_http_method_is_case_insensitive(self):
        result = self.matcher.match_route(
            "get", "/api/v1/orders/{id}"
        )

        self.assertTrue(result["declared"])

    def test_matches_multiple_observed_routes(self):
        observed = [
            {"method": "GET", "route": "/api/v1/orders/{id}"},
            {"method": "DELETE", "route": "/api/v1/orders/{id}"},
            {"method": "POST", "route": "/api/v1/orders"},
        ]

        results = self.matcher.match_observed_routes(observed)

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]["declared"])
        self.assertFalse(results[1]["declared"])
        self.assertTrue(results[2]["declared"])

    def test_empty_contract_list(self):
        matcher = RouteMatcher([])

        result = matcher.match_route(
            "GET", "/api/v1/orders"
        )

        self.assertFalse(result["declared"])

    def test_ignores_invalid_contract_entries(self):
        matcher = RouteMatcher([
            {"method": "", "path": "/api/v1/orders"},
            {"method": "GET", "path": ""},
            {},
        ])

        self.assertFalse(
            matcher.match_route(
                "GET", "/api/v1/orders"
            )["declared"]
        )


if __name__ == "__main__":
    unittest.main()