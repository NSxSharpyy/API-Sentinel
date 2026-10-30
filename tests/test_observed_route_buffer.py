import unittest

from src.observed_route_buffer import ObservedRouteBuffer


class TestObservedRouteBuffer(unittest.TestCase):

    def setUp(self):
        self.buffer = ObservedRouteBuffer()

    def test_records_new_route(self):
        result = self.buffer.record("GET", "/api/v1/users")

        self.assertEqual(result["method"], "GET")
        self.assertEqual(result["route"], "/api/v1/users")
        self.assertEqual(result["observations"], 1)

    def test_normalizes_dynamic_routes(self):
        self.buffer.record("GET", "/api/v1/orders/8921")
        self.buffer.record("GET", "/api/v1/orders/7354")

        self.assertEqual(self.buffer.get_count(), 1)

        routes = self.buffer.get_routes()
        self.assertEqual(routes[0]["route"], "/api/v1/orders/{id}")
        self.assertEqual(routes[0]["observations"], 2)

    def test_different_methods_are_separate_routes(self):
        self.buffer.record("GET", "/api/v1/orders")
        self.buffer.record("POST", "/api/v1/orders")

        self.assertEqual(self.buffer.get_count(), 2)

    def test_method_is_case_insensitive(self):
        self.buffer.record("get", "/api/v1/users")
        self.buffer.record("GET", "/api/v1/users")

        self.assertEqual(self.buffer.get_count(), 1)
        self.assertEqual(self.buffer.get_routes()[0]["observations"], 2)

    def test_rejects_empty_method(self):
        with self.assertRaises(ValueError):
            self.buffer.record("", "/api/v1/users")

    def test_rejects_empty_url(self):
        with self.assertRaises(ValueError):
            self.buffer.record("GET", "")

    def test_clear_removes_all_routes(self):
        self.buffer.record("GET", "/api/v1/users")
        self.buffer.clear()

        self.assertEqual(self.buffer.get_count(), 0)
        self.assertEqual(self.buffer.get_routes(), [])

    def test_first_seen_is_recorded(self):
        result = self.buffer.record("GET", "/api/v1/users")

        self.assertIn("first_seen", result)
        self.assertTrue(result["first_seen"])


if __name__ == "__main__":
    unittest.main()