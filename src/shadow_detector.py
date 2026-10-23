"""Shadow API detection for API-Sentinel."""

from __future__ import annotations

from typing import Any


class ShadowAPIDetector:
    """Detect observed API endpoints missing from official contracts."""

    def __init__(self, route_matcher):
        self.route_matcher = route_matcher

    def detect(self, observed_routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Detect shadow APIs from observed runtime routes.

        A route is considered a Shadow API when it is observed at runtime
        but is not declared in the official API contract.
        """

        findings = []

        matches = self.route_matcher.match_observed_routes(observed_routes)

        for match in matches:
            if not match["declared"]:
                findings.append(
                    {
                        "method": match["method"],
                        "route": match["route"],
                        "status": "shadow",
                        "finding": "Shadow API",
                        "reason": (
                            "Observed runtime endpoint is missing "
                            "from the official API contract."
                        ),
                    }
                )

        return findings