"""Shadow API detection for API-Sentinel."""

from __future__ import annotations

from typing import Any


class ShadowAPIDetector:
    """Detect observed API endpoints missing from official contracts."""

    def __init__(self, route_matcher):
        self.route_matcher = route_matcher

    def detect(
        self,
        observed_routes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Detect shadow APIs from observed runtime routes.

        A route is considered a Shadow API when it is observed at runtime
        but is not declared in the official API contract.

        Duplicate observations of the same method-route pair produce
        only one finding.
        """

        findings = []
        seen_routes = set()

        matches = self.route_matcher.match_observed_routes(
            observed_routes
        )

        for match in matches:
            if match["declared"]:
                continue

            method = str(match["method"]).strip().upper()
            route = str(match["route"]).strip()

            if not method or not route:
                continue

            route_key = (method, route)

            if route_key in seen_routes:
                continue

            seen_routes.add(route_key)

            findings.append(
                {
                    "method": method,
                    "route": route,
                    "status": "shadow",
                    "finding": "Shadow API",
                    "reason": (
                        "Observed runtime endpoint is missing "
                        "from the official API contract."
                    ),
                }
            )

        return findings