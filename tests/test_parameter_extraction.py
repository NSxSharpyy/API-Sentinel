import unittest

from src.route_normalizer import normalize_route


class TestParameterExtraction(unittest.TestCase):

    def test_numeric_path_parameter(self):
        self.assertEqual(
            normalize_route("/api/v1/orders/8921"),
            "/api/v1/orders/{id}"
        )

    def test_query_parameter_is_ignored(self):
        self.assertEqual(
            normalize_route("/api/v1/orders/8921?status=paid"),
            "/api/v1/orders/{id}"
        )

    def test_multiple_query_parameters(self):
        self.assertEqual(
            normalize_route(
                "/api/v1/orders/8921?status=paid&sort=date"
            ),
            "/api/v1/orders/{id}"
        )

    def test_trailing_slash(self):
        self.assertEqual(
            normalize_route("/api/v1/users/42/"),
            "/api/v1/users/{id}"
        )

    def test_root_route(self):
        self.assertEqual(
            normalize_route("/"),
            "/"
        )

    def test_non_numeric_path_parameter(self):
        self.assertEqual(
            normalize_route("/api/v1/users/shirish"),
            "/api/v1/users/shirish"
        )

    def test_empty_input_raises_error(self):
        with self.assertRaises(ValueError):
            normalize_route("")


if __name__ == "__main__":
    unittest.main()