import unittest
from unittest import result

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

    def test_matches_dynamic_observed_route(self):
        matcher = RouteMatcher([
        {
            "method": "GET",
            "path": "/api/v1/orders/{id}",
        }
    ])

        result = matcher.match_route(
        "GET",
        "/api/v1/orders/8921",
    )

        self.assertTrue(result["declared"])
        self.assertEqual(result["route"], "/api/v1/orders/{id}")
        self.assertEqual(result["status"], "declared")

    def test_matches_observed_route_with_query_parameters(self):
        matcher = RouteMatcher([
            {
                "method": "GET",
                "path": "/api/v1/orders/{id}",
            }
        ])

        result = matcher.match_route(
            "GET",
            "/api/v1/orders/8921?status=paid",
        )

        self.assertTrue(result["declared"])
        self.assertEqual(
            result["route"],
            "/api/v1/orders/{id}",
        )

    def test_matches_observed_route_with_trailing_slash(self):
        matcher = RouteMatcher([
            {
                "method": "GET",
                "path": "/api/v1/users/{id}",
            }
        ])

        result = matcher.match_route(
            "GET",
            "/api/v1/users/42/",
        )

        self.assertTrue(result["declared"])
        self.assertEqual(
            result["route"],
            "/api/v1/users/{id}",
        )

    def test_different_method_is_undocumented(self):
        matcher = RouteMatcher([
            {
                "method": "GET",
                "path": "/api/v1/orders/{id}",
            }
        ])

        result = matcher.match_route(
            "POST",
            "/api/v1/orders/8921",
        )

        self.assertFalse(result["declared"])
        self.assertEqual(
            result["status"],
            "potentially_undocumented",
        )

    def test_ignores_invalid_observed_entries(self):
        observed = [
            None,
            {},
            "invalid-record",
            {
                "method": "",
                "route": "/api/v1/users/42",
            },
            {
                "method": "GET",
                "route": "",
            },
            {
                "method": None,
                "route": "/api/v1/users/42",
            },
            {
                "method": "GET",
                "route": None,
            },
        ]

        results = self.matcher.match_observed_routes(observed)

        self.assertEqual(results, [])

    def test_match_route_rejects_invalid_method(self):
        with self.assertRaises(ValueError):
            self.matcher.match_route(
                None,
                "/api/v1/users/42",
            )

    def test_match_route_rejects_invalid_route(self):
        with self.assertRaises(ValueError):
            self.matcher.match_route(
                "GET",
                None,
            )

    def test_match_route_rejects_empty_method(self):
        with self.assertRaises(ValueError):
            self.matcher.match_route(
                "",
                "/api/v1/users/42",
            )

    def test_match_route_rejects_empty_route(self):
        with self.assertRaises(ValueError):
            self.matcher.match_route(
                "GET",
                "",
            )

    def test_matches_multiple_dynamic_routes(self):
        matcher = RouteMatcher([
            {
                "method": "GET",
                "path": "/api/v1/orders/{id}",
            },
            {
                "method": "GET",
                "path": "/api/v1/users/{id}",
            },
            {
                "method": "POST",
                "path": "/api/v1/orders",
            },
        ])

        observed = [
            {
                "method": "GET",
                "route": "/api/v1/orders/8921",
            },
            {
                "method": "GET",
                "route": "/api/v1/users/42",
            },
            {
                "method": "POST",
                "route": "/api/v1/orders",
            },
            {
                "method": "DELETE",
                "route": "/api/v1/orders/8921",
            },
        ]

        results = matcher.match_observed_routes(observed)

        self.assertEqual(len(results), 4)

        self.assertTrue(results[0]["declared"])
        self.assertTrue(results[1]["declared"])
        self.assertTrue(results[2]["declared"])
        self.assertFalse(results[3]["declared"])

        self.assertEqual(
            results[3]["status"],
            "potentially_undocumented",
        )


if __name__ == "__main__":
    unittest.main()