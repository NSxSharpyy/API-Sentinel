import time
import unittest

from src.concurrency import ConcurrentRouteProcessor


class TestConcurrencyPerformance(unittest.TestCase):

    def test_concurrent_processing(self):
        routes = [
            {"id": 1},
            {"id": 2},
            {"id": 3},
            {"id": 4},
        ]

        def slow_processor(route):
            time.sleep(0.1)
            return route["id"]

        processor = ConcurrentRouteProcessor(max_workers=4)

        start = time.perf_counter()

        result = processor.process(
            routes,
            slow_processor,
        )

        elapsed = time.perf_counter() - start

        self.assertEqual(result, [1, 2, 3, 4])

        # Four 0.1-second tasks should complete substantially
        # faster than approximately 0.4 seconds with 4 workers.
        self.assertLess(elapsed, 0.30)


if __name__ == "__main__":
    unittest.main()