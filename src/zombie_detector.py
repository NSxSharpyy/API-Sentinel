class ZombieAPIDetector:
    """Detect deprecated or inactive API endpoints that still receive traffic."""

    def __init__(self, official_contract):
        if not isinstance(official_contract, dict):
            raise ValueError("Official contract must be a dictionary.")

        self.official_contract = official_contract
        self.zombie_apis = []

    def _is_inactive(self, endpoint_details):
        """Check whether an OpenAPI endpoint is deprecated or inactive."""

        if not isinstance(endpoint_details, dict):
            return False

        # OpenAPI operation-level deprecated flag.
        for method, details in endpoint_details.items():
            if not isinstance(details, dict):
                continue

            if details.get("deprecated") is True:
                return True

            # Support an explicit inactive marker when supplied
            # by the project contract.
            if details.get("inactive") is True:
                return True

        return False

    def analyze(self, observed_routes):
        """
        Find deprecated/inactive contract endpoints receiving live traffic.

        Expected observed_routes:

        [
            {
                "method": "GET",
                "route": "/api/v1/old-users"
            }
        ]
        """

        paths = self.official_contract.get("paths", {})

        if not isinstance(paths, dict):
            raise ValueError("Official contract paths must be a dictionary.")

        findings = []

        for observed in observed_routes:
            if not isinstance(observed, dict):
                continue

            method = observed.get("method", "").strip().upper()
            route = observed.get("route", "").strip()

            if not method or not route:
                continue

            endpoint_details = paths.get(route)

            # Route is not declared at all.
            # That case belongs to Shadow API detection.
            if not isinstance(endpoint_details, dict):
                continue

            method_details = endpoint_details.get(method.lower())

            if not isinstance(method_details, dict):
                continue

            if (
                method_details.get("deprecated") is True
                or method_details.get("inactive") is True
            ):
                findings.append(
                    {
                        "method": method,
                        "route": route,
                        "status": "ZOMBIE_API",
                        "reason": (
                            "Declared API endpoint is deprecated or inactive "
                            "but still receives live traffic."
                        ),
                    }
                )

        self.zombie_apis = findings

        return findings

    def count(self):
        """Return the number of detected Zombie APIs."""

        return len(self.zombie_apis)