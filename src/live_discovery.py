"""
Live Shadow API Discovery

Connects observed runtime traffic with the official API contract
and classifies each observed endpoint as:

- OFFICIAL_API
- SHADOW_API
- ZOMBIE_API
"""

from typing import Any, Dict, Iterable, List, Tuple

from src.contract_differ import compare_route_to_contract
from src.risk_scoring import EndpointRiskScorer


class LiveShadowDiscovery:
    """Classify observed runtime API traffic against an official contract."""

    SUPPORTED_METHODS = {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "TRACE",
    }

    def __init__(self, official_contract: Dict[str, Any]):
        if not isinstance(official_contract, dict):
            raise ValueError("official_contract must be a dictionary")

        self.official_contract = official_contract

    def _extract_declared_routes(self) -> List[Dict[str, Any]]:
        """
        Extract HTTP method and path pairs from the OpenAPI contract.

        Returns:
            A list containing dictionaries with:
            - method
            - path
            - deprecated
        """

        declared_routes = []

        paths = self.official_contract.get("paths", {})

        if not isinstance(paths, dict):
            return declared_routes

        for path, path_item in paths.items():

            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():

                normalized_method = str(method).strip().upper()

                if normalized_method not in self.SUPPORTED_METHODS:
                    continue

                if not isinstance(operation, dict):
                    operation = {}

                declared_routes.append(
                    {
                        "method": normalized_method,
                        "path": str(path).strip(),
                        "deprecated": operation.get(
                            "deprecated",
                            False,
                        ),
                    }
                )

        return declared_routes

    @staticmethod
    def _normalize_observed_route(
        observed_route: Any,
    ) -> Tuple[str, str]:
        """
        Normalize an observed route into:

            (HTTP_METHOD, PATH)

        Supported input formats:

            "/users"

            ("GET", "/users")

            {"method": "GET", "route": "/users"}

            {"method": "GET", "path": "/users"}
        """

        if isinstance(observed_route, tuple):
            if len(observed_route) != 2:
                raise ValueError(
                    "Observed route tuple must contain method and route"
                )

            method, route = observed_route

        elif isinstance(observed_route, dict):
            method = observed_route.get("method")
            route = observed_route.get(
                "route",
                observed_route.get("path"),
            )

        elif isinstance(observed_route, str):
            # Backward compatibility:
            # old callers can still provide route-only values.
            method = None
            route = observed_route

        else:
            raise ValueError(
                "Observed route must be a string, tuple, or dictionary"
            )

        if not isinstance(route, str) or not route.strip():
            raise ValueError(
                "Observed route must contain a non-empty path"
            )

        normalized_route = route.strip()

        if method is None:
            return "", normalized_route

        if not isinstance(method, str) or not method.strip():
            raise ValueError(
                "Observed HTTP method must be a non-empty string"
            )

        normalized_method = method.strip().upper()

        if normalized_method not in LiveShadowDiscovery.SUPPORTED_METHODS:
            raise ValueError(
                f"Unsupported HTTP method: {normalized_method}"
            )

        return normalized_method, normalized_route

    @staticmethod
    def _route_matches(
        observed_method: str,
        observed_route: str,
        declared_method: str,
        declared_path: str,
    ) -> bool:
        """
        Match an observed method/path against one declared contract route.
        """

        if observed_method and observed_method != declared_method:
            return False

        normalized_observed = observed_route.rstrip("/") or "/"
        normalized_declared = declared_path.rstrip("/") or "/"

        if normalized_observed == normalized_declared:
            return True

        # Support OpenAPI path parameters such as:
        # /users/{id}
        # /orders/{order_id}
        observed_segments = normalized_observed.strip("/").split("/")
        declared_segments = normalized_declared.strip("/").split("/")

        if len(observed_segments) != len(declared_segments):
            return False

        for observed_segment, declared_segment in zip(
            observed_segments,
            declared_segments,
        ):
            if (
                declared_segment.startswith("{")
                and declared_segment.endswith("}")
            ):
                continue

            if observed_segment != declared_segment:
                return False

        return True

    def discover(
        self,
        observed_routes: Iterable[Any],
    ) -> List[Dict[str, str]]:
        """
        Analyze observed routes and return their classifications.

        Method-aware input is preferred.

        Examples:

            [
                ("GET", "/users"),
                ("DELETE", "/users"),
            ]

        or:

            [
                {"method": "GET", "path": "/users"},
                {"method": "DELETE", "path": "/users"},
            ]

        Route-only strings remain supported for backward compatibility.
        """

        if observed_routes is None:
            raise ValueError("observed_routes cannot be None")

        results = []

        declared_routes = self._extract_declared_routes()

        for observed_route in observed_routes:

            try:
                method, route = self._normalize_observed_route(
                    observed_route
                )
            except ValueError:
                continue

            matching_contracts = [
                contract
                for contract in declared_routes
                if self._route_matches(
                    method,
                    route,
                    contract["method"],
                    contract["path"],
                )
            ]

            if matching_contracts:
                contract = matching_contracts[0]

                if contract["deprecated"] is True:
                    status = "ZOMBIE_API"
                else:
                    status = "OFFICIAL_API"

            else:
                status = "SHADOW_API"

            result = {
                "route": route,
                "status": status,
            }

            if method:
                result["method"] = method

            results.append(result)

        return results

    def discover_shadow_apis(
        self,
        observed_routes: Iterable[Any],
    ) -> List[Dict[str, str]]:
        """Return only Shadow API findings."""

        results = self.discover(observed_routes)

        return [
            result
            for result in results
            if result["status"] == "SHADOW_API"
        ]

    def discover_zombie_apis(
        self,
        observed_routes: Iterable[Any],
    ) -> List[Dict[str, str]]:
        """Return only Zombie API findings."""

        results = self.discover(observed_routes)

        return [
            result
            for result in results
            if result["status"] == "ZOMBIE_API"
        ]

    def discover_with_risk_scoring(
        self,
        observed_routes: Iterable[Any],
        scorer: EndpointRiskScorer = None,
    ) -> List[Dict[str, Any]]:
            """
            Discover observed APIs and attach risk scores.

        Existing discovery classification remains unchanged.
        """

            risk_scorer = scorer or EndpointRiskScorer()

            discovered_endpoints = self.discover(observed_routes)

            return risk_scorer.score_endpoints(discovered_endpoints)