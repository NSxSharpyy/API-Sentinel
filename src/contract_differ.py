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

    @staticmethod
    def _find_zombie_routes(spec):
        """Return routes marked as deprecated in the official contract."""

        zombie_routes = set()

        paths = spec.get("paths", {})

        if not isinstance(paths, dict):
            return zombie_routes

        for path, path_item in paths.items():

            if not isinstance(path_item, dict):
                continue

            for method, details in path_item.items():

                if method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                    "trace",
                }:
                    continue

                if not isinstance(details, dict):
                    continue

                if details.get("deprecated") is True:
                    zombie_routes.add(
                        (
                            method.upper(),
                            path,
                        )
                    )

        return zombie_routes

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

        zombie_routes = sorted(
            self._find_zombie_routes(
                self.official_spec
            ) & live_routes
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
            "zombie": [
                {
                    "method": method,
                    "path": path,
                    "status": "ZOMBIE_API",
                }
                for method, path in zombie_routes
            ],
        }

    def diff(self):
        """Perform complete contract diff."""

        route_diff = self.diff_routes()

        return {
            "summary": {
                "official_routes": len(
                    self._extract_routes(
                        self.official_spec
                    )
                ),
                "live_routes": len(
                    self._extract_routes(
                        self.live_spec
                    )
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
                "zombie": len(
                    route_diff["zombie"]
                ),
            },
            "differences": route_diff,
        }


def compare_route_to_contract(route, official_contract):
    """
    Classify an observed runtime route against an
    official OpenAPI contract.

    Returns:
        OFFICIAL_API
        SHADOW_API
        ZOMBIE_API
    """

    if not isinstance(route, str):
        return "SHADOW_API"

    if not isinstance(official_contract, dict):
        return "SHADOW_API"

    normalized_route = route.strip()

    if not normalized_route:
        return "SHADOW_API"

    paths = official_contract.get("paths", {})

    if not isinstance(paths, dict):
        return "SHADOW_API"

    # Check whether the route exists in the official contract.
    if normalized_route not in paths:
        return "SHADOW_API"

    path_item = paths.get(normalized_route)

    if not isinstance(path_item, dict):
        return "SHADOW_API"

    # Check all HTTP methods for this route.
    for method, details in path_item.items():

        if method.lower() not in {
            "get",
            "post",
            "put",
            "patch",
            "delete",
            "head",
            "options",
            "trace",
        }:
            continue

        if not isinstance(details, dict):
            continue

        if details.get("deprecated") is True:
            return "ZOMBIE_API"

    return "OFFICIAL_API"