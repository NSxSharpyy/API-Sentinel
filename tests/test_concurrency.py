import time
import unittest

from src.concurrency import ConcurrentRouteProcessor


class TestConcurrentRouteProcessor(unittest.TestCase):

    def test_process_empty_routes(self):
        processor = ConcurrentRouteProcessor(max_workers=2)

        result = processor.process(
            [],
            lambda route: route,
        )

        self.assertEqual(result, [])

    def test_process_routes(self):
        processor = ConcurrentRouteProcessor(max_workers=2)

        routes = [
            {"method": "GET", "route": "/api/users"},
            {"method": "GET", "route": "/api/orders"},
        ]

        result = processor.process(
            routes,
            lambda route: route["route"],
        )

        self.assertEqual(
            result,
            [
                "/api/users",
                "/api/orders",
            ],
        )

    def test_preserves_input_order(self):
        processor = ConcurrentRouteProcessor(max_workers=3)

        routes = [
            {"id": 1, "delay": 0.03},
            {"id": 2, "delay": 0.01},
            {"id": 3, "delay": 0.02},
        ]

        def process(route):
            time.sleep(route["delay"])
            return route["id"]

        result = processor.process(routes, process)

        self.assertEqual(result, [1, 2, 3])

    def test_single_worker(self):
        processor = ConcurrentRouteProcessor(max_workers=1)

        routes = [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ]

        result = processor.process(
            routes,
            lambda route: route["id"],
        )

        self.assertEqual(result, [1, 2, 3])

    def test_invalid_worker_count(self):
        with self.assertRaises(ValueError):
            ConcurrentRouteProcessor(max_workers=0)

    def test_invalid_worker_type(self):
        with self.assertRaises(TypeError):
            ConcurrentRouteProcessor(max_workers="4")

    def test_processor_exception_propagates(self):
        processor = ConcurrentRouteProcessor(max_workers=2)

        routes = [
            {"id": 1},
            {"id": 2},
        ]

        def failing_processor(route):
            if route["id"] == 2:
                raise RuntimeError("processing failed")

            return route["id"]

        with self.assertRaises(RuntimeError):
            processor.process(routes, failing_processor)


if __name__ == "__main__":
    unittest.main()