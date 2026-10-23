from concurrent.futures import ThreadPoolExecutor, as_completed


class ConcurrentRouteProcessor:
    """Process API routes concurrently with a bounded worker pool."""

    def __init__(self, max_workers=4):
        if not isinstance(max_workers, int):
            raise TypeError("max_workers must be an integer.")

        if max_workers < 1:
            raise ValueError("max_workers must be at least 1.")

        self.max_workers = max_workers

    def _process_one(self, processor, route):
        """Process one route using the supplied processor."""

        return processor(route)

    def process(self, routes, processor):
        """
        Process routes concurrently.

        Args:
            routes: Iterable of route objects.
            processor: Callable that accepts one route.

        Returns:
            List of processed results in input order.
        """

        routes = list(routes)

        if not routes:
            return []

        results = [None] * len(routes)

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            future_to_index = {
                executor.submit(
                    self._process_one,
                    processor,
                    route,
                ): index
                for index, route in enumerate(routes)
            }

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                results[index] = future.result()

        return results