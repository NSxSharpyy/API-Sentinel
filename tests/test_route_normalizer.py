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
        self.assertEqual(
            normalize_route("/"),
            "/",
        )

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            normalize_route("")

    # ---------------------------------------------------------
    # Issue #1 regression tests
    # ---------------------------------------------------------

    def test_normalizes_uuid_id(self):
        """UUID path segments must be treated as dynamic IDs."""

        self.assertEqual(
            normalize_route(
                "/api/v1/users/550e8400-e29b-41d4-a716-446655440000"
            ),
            "/api/v1/users/{id}",
        )

    def test_preserves_long_static_route_name(self):
        """Long static route names must not become {id}."""

        self.assertEqual(
            normalize_route(
                "/api/documentation"
            ),
            "/api/documentation",
        )

    def test_preserves_long_static_alphanumeric_route(self):
        """Long alphanumeric static segments must remain unchanged."""

        self.assertEqual(
            normalize_route(
                "/api/administration"
            ),
            "/api/administration",
        )

    def test_preserves_mixed_static_and_dynamic_segments(self):
        """Dynamic IDs should normalize without changing static segments."""

        self.assertEqual(
            normalize_route(
                "/api/v1/users/123/orders"
            ),
            "/api/v1/users/{id}/orders",
        )


if __name__ == "__main__":
    unittest.main()