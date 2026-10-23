"""
Live Shadow API Discovery

Connects observed runtime traffic with the official API contract
and classifies each observed endpoint as:

- OFFICIAL_API
- SHADOW_API
- ZOMBIE_API
"""

from typing import Any, Dict, Iterable, List

from src.contract_differ import compare_route_to_contract


class LiveShadowDiscovery:
    """Classify observed runtime API traffic against an official contract."""

    def __init__(self, official_contract: Dict[str, Any]):
        if not isinstance(official_contract, dict):
            raise ValueError("official_contract must be a dictionary")

        self.official_contract = official_contract

    def discover(
        self,
        observed_routes: Iterable[str],
    ) -> List[Dict[str, str]]:
        """
        Analyze observed routes and return their classifications.
        """

        if observed_routes is None:
            raise ValueError("observed_routes cannot be None")

        results = []

        for route in observed_routes:
            if not isinstance(route, str):
                continue

            normalized_route = route.strip()

            if not normalized_route:
                continue

            status = compare_route_to_contract(
                normalized_route,
                self.official_contract,
            )

            results.append(
                {
                    "route": normalized_route,
                    "status": status,
                }
            )

        return results

    def discover_shadow_apis(
        self,
        observed_routes: Iterable[str],
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
        observed_routes: Iterable[str],
    ) -> List[Dict[str, str]]:
        """Return only Zombie API findings."""

        results = self.discover(observed_routes)

        return [
            result
            for result in results
            if result["status"] == "ZOMBIE_API"
        ]