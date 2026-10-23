import unittest

from src.route_normalizer import normalize_route


class TestRouteNormalizer(unittest.TestCase):

    def test_normalizes_numeric_order_id(self):
        self.assertEqual(
            normalize_route("/api/v1/orders/8921"),
            "/api/v1/orders/{id}",
        )

    def test_normalizes_different_numeric_ids(self):
        self.assertEqual(
            normalize_route("/api/v1/orders/7354"),
            "/api/v1/orders/{id}",
        )

    def test_normalizes_user_id(self):
        self.assertEqual(
            normalize_route("/api/v1/users/42"),
            "/api/v1/users/{id}",
        )

    def test_removes_trailing_slash(self):
        self.assertEqual(
            normalize_route("/api/v1/orders/8921/"),
            "/api/v1/orders/{id}",
        )

    def test_ignores_query_parameters(self):
        self.assertEqual(
            normalize_route("/api/v1/orders/8921?status=paid"),
            "/api/v1/orders/{id}",
        )

    def test_preserves_root_route(self):
        self.assertEqual(normalize_route("/"), "/")

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            normalize_route("")


if __name__ == "__main__":
    unittest.main()