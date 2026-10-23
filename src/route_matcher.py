from .route_normalizer import normalize_route


class RouteMatcher:
    """Match observed API routes against declared API contracts."""

    def __init__(self, declared_contracts):
        self.declared_routes = set()

        for contract in declared_contracts:
            method = contract.get("method", "").upper()
            path = contract.get("path", "")

            if method and path:
                try:
                    normalized_path = normalize_route(path)
                    self.declared_routes.add((method, normalized_path))
                except ValueError:
                    continue

    def match_route(self, method, observed_route):
        """Check whether an observed API route exists in the contract."""

        normalized_method = method.strip().upper()
        normalized_route = normalize_route(observed_route)

        key = (normalized_method, normalized_route)

        declared = key in self.declared_routes

        return {
            "method": normalized_method,
            "route": normalized_route,
            "declared": declared,
            "status": (
                "declared"
                if declared
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