import re


class ZombieAPIDetector:
    """Detect deprecated or inactive API endpoints that still receive traffic."""

    SUPPORTED_METHODS = {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
        "TRACE",
    }

    def __init__(self, official_contract):
        if not isinstance(official_contract, dict):
            raise ValueError("Official contract must be a dictionary.")

        self.official_contract = official_contract
        self.zombie_apis = []

    def _is_inactive(self, endpoint_details):
        """
        Check whether an OpenAPI operation is explicitly deprecated
        or marked inactive.

        Important:
        deprecated=True alone is treated as Zombie according to the
        current project contract/tests. It is not claimed to prove
        that the endpoint has been permanently retired.
        """

        if not isinstance(endpoint_details, dict):
            return False

        for method, details in endpoint_details.items():
            if method.lower() not in self.SUPPORTED_METHODS:
                continue

            if not isinstance(details, dict):
                continue

            if details.get("deprecated") is True:
                return True

            if details.get("inactive") is True:
                return True

        return False

    def _match_path_template(self, observed_route, declared_route):
        """
        Match an observed runtime route against an OpenAPI path template.

        Example:
            observed: /api/v1/users/123
            declared: /api/v1/users/{id}

        returns True.

        Static path names must remain exact matches.
        """

        if not isinstance(observed_route, str):
            return False

        if not isinstance(declared_route, str):
            return False

        observed = observed_route.strip()
        declared = declared_route.strip()

        if not observed or not declared:
            return False

        if observed != "/" and observed.endswith("/"):
            observed = observed.rstrip("/")

        if declared != "/" and declared.endswith("/"):
            declared = declared.rstrip("/")

        observed_segments = observed.split("/")
        declared_segments = declared.split("/")

        if len(observed_segments) != len(declared_segments):
            return False

        parameter_pattern = re.compile(r"^\{[^{}]+\}$")

        for observed_segment, declared_segment in zip(
            observed_segments,
            declared_segments,
        ):
            # OpenAPI path parameter, e.g. {id}, {userId}
            if parameter_pattern.fullmatch(declared_segment):
                if not observed_segment:
                    return False

                continue

            # Static segment must match exactly.
            if observed_segment != declared_segment:
                return False

        return True

    def _find_endpoint(self, observed_route, method):
        """
        Find the OpenAPI operation matching an observed route and method.

        Returns:
            tuple(path, operation_details)
            or
            (None, None)
        """

        paths = self.official_contract.get("paths", {})

        if not isinstance(paths, dict):
            raise ValueError(
                "Official contract paths must be a dictionary."
            )

        method = method.upper()

        for declared_route, endpoint_details in paths.items():
            if not isinstance(endpoint_details, dict):
                continue

            if not self._match_path_template(
                observed_route,
                declared_route,
            ):
                continue

            method_details = endpoint_details.get(method.lower())

            if not isinstance(method_details, dict):
                continue

            return declared_route, method_details

        return None, None

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

        A route is considered Zombie only when:

        1. The route exists in the official contract.
        2. The HTTP method matches.
        3. The declared operation is deprecated or explicitly inactive.

        Undocumented routes are ignored here because they belong to
        Shadow API detection.
        """

        if observed_routes is None:
            raise ValueError("observed_routes cannot be None.")

        findings = []

        for observed in observed_routes:
            if not isinstance(observed, dict):
                continue

            method = observed.get("method", "")
            route = observed.get("route", "")

            if not isinstance(method, str):
                continue

            if not isinstance(route, str):
                continue

            method = method.strip().upper()
            route = route.strip()

            if not method or not route:
                continue

            if method not in self.SUPPORTED_METHODS:
                continue

            declared_route, method_details = self._find_endpoint(
                route,
                method,
            )

            # Undocumented endpoint.
            # Shadow API detector handles this case.
            if declared_route is None:
                continue

            if not isinstance(method_details, dict):
                continue

            is_deprecated = method_details.get("deprecated") is True
            is_inactive = method_details.get("inactive") is True

            if not (is_deprecated or is_inactive):
                continue

            reasons = []

            if is_deprecated:
                reasons.append("deprecated")

            if is_inactive:
                reasons.append("inactive")

            findings.append(
                {
                    "method": method,
                    "route": route,
                    "status": "ZOMBIE_API",
                    "reason": (
                        "Declared API endpoint is "
                        + " and ".join(reasons)
                        + " but still receives live traffic."
                    ),
                }
            )

        self.zombie_apis = findings

        return findings

    def count(self):
        """Return the number of detected Zombie APIs."""

        return len(self.zombie_apis)