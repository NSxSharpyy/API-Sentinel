from .route_normalizer import normalize_route


class RouteMatcher:
    """Match observed API routes against declared API contracts."""

    def __init__(self, declared_contracts):
        self.declared_routes = set()

        if not isinstance(declared_contracts, (list, tuple)):
            return

        for contract in declared_contracts:
            if not isinstance(contract, dict):
                continue

            method = contract.get("method", "")
            path = contract.get("path", "")

            if not isinstance(method, str) or not isinstance(path, str):
                continue

            method = method.strip().upper()
            path = path.strip()

            if not method or not path:
                continue

            try:
                normalized_path = normalize_route(path)
                self.declared_routes.add(
                    (method, normalized_path)
                )
            except ValueError:
                continue

    def match_route(self, method, observed_route):
        """Check whether an observed API route exists in the contract."""

        if not isinstance(method, str):
            raise ValueError("HTTP method must be a string.")

        if not isinstance(observed_route, str):
            raise ValueError("Observed route must be a string.")

        normalized_method = method.strip().upper()

        if not normalized_method:
            raise ValueError("HTTP method cannot be empty.")

        if not observed_route.strip():
            raise ValueError("Observed route cannot be empty.")

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
        """Match multiple observed routes against declared contracts.

        Malformed route records are skipped so one invalid observation
        does not crash the complete discovery process.
        """

        if observed_routes is None:
            raise ValueError("observed_routes cannot be None.")

        if not isinstance(observed_routes, (list, tuple)):
            raise ValueError(
                "observed_routes must be a list or tuple."
            )

        results = []

        for route in observed_routes:
            if not isinstance(route, dict):
                continue

            method = route.get("method")
            observed_route = route.get("route")

            if not isinstance(method, str):
                continue

            if not isinstance(observed_route, str):
                continue

            if not method.strip() or not observed_route.strip():
                continue

            try:
                result = self.match_route(
                    method,
                    observed_route,
                )
            except ValueError:
                continue

            results.append(result)

        return results