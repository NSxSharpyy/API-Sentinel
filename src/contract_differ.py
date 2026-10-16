class ContractDiffEngine:
    """Compare dynamically generated live API schemas
    against official OpenAPI contract schemas.
    """

    def __init__(self, official_spec, live_spec):
        self.official_spec = official_spec or {}
        self.live_spec = live_spec or {}

    @staticmethod
    def _extract_routes(spec):
        """Return a set of (HTTP method, path) pairs."""

        routes = set()

        paths = spec.get("paths", {})

        if not isinstance(paths, dict):
            return routes

        for path, path_item in paths.items():

            if not isinstance(path_item, dict):
                continue

            for method in path_item:

                if method.lower() in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                    "trace",
                }:
                    routes.add(
                        (
                            method.upper(),
                            path,
                        )
                    )

        return routes

    def diff_routes(self):
        """Compare official and live API routes."""

        official_routes = self._extract_routes(
            self.official_spec
        )

        live_routes = self._extract_routes(
            self.live_spec
        )

        live_only = sorted(
            live_routes - official_routes
        )

        official_only = sorted(
            official_routes - live_routes
        )

        common = sorted(
            official_routes & live_routes
        )

        return {
            "live_only": [
                {
                    "method": method,
                    "path": path,
                }
                for method, path in live_only
            ],
            "official_only": [
                {
                    "method": method,
                    "path": path,
                }
                for method, path in official_only
            ],
            "common": [
                {
                    "method": method,
                    "path": path,
                }
                for method, path in common
            ],
        }

    def diff(self):
        """Perform complete contract diff."""

        route_diff = self.diff_routes()

        return {
            "summary": {
                "official_routes": len(
                    self._extract_routes(self.official_spec)
                ),
                "live_routes": len(
                    self._extract_routes(self.live_spec)
                ),
                "live_only": len(
                    route_diff["live_only"]
                ),
                "official_only": len(
                    route_diff["official_only"]
                ),
                "common": len(
                    route_diff["common"]
                ),
            },
            "differences": route_diff,
        }