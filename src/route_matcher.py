class RouteMatcher:
    """Match observed API routes against declared API contracts."""

    def __init__(self, declared_contracts):
        self.declared_routes = set()

        for contract in declared_contracts:
            method = contract.get("method", "").upper()
            path = contract.get("path", "")

            if method and path:
                self.declared_routes.add((method, path))

    def match_route(self, method, observed_route):
        """Check whether an observed route exists in the contract."""

        key = (method.strip().upper(), observed_route)

        return {
            "method": key[0],
            "route": key[1],
            "declared": key in self.declared_routes,
            "status": (
                "declared"
                if key in self.declared_routes
                else "potentially_undocumented"
            ),
        }

    def match_observed_routes(self, observed_routes):
        """Match multiple observed routes against declared contracts."""

        results = []

        for route in observed_routes:
            result = self.match_route(
                route.get("method", ""),
                route.get("route", ""),
            )
            results.append(result)

        return results