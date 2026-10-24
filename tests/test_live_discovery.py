import json
import unittest

from src.live_discovery import LiveShadowDiscovery


class TestLiveShadowDiscovery(unittest.TestCase):

    def setUp(self):
        # MOCK DATA — TEMPORARY
        self.official_contract = {
            "openapi": "3.0.0",
            "info": {
                "title": "Mock API",
                "version": "1.0.0",
            },
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Successful response"
                            }
                        }
                    }
                },
                "/orders": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Successful response"
                            }
                        }
                    }
                },
                "/old-api": {
                    "get": {
                        "deprecated": True,
                        "responses": {
                            "200": {
                                "description": "Deprecated response"
                            }
                        }
                    }
                },
            },
        }

        self.observed_routes = [
            "/users",
            "/orders",
            "/admin/debug",
            "/old-api",
        ]

    def test_live_discovery_classification(self):

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        results = discovery.discover(
            self.observed_routes
        )

        self.assertEqual(len(results), 4)

        status_map = {
            item["route"]: item["status"]
            for item in results
        }

        self.assertEqual(
            status_map["/users"],
            "OFFICIAL_API",
        )

        self.assertEqual(
            status_map["/orders"],
            "OFFICIAL_API",
        )

        self.assertEqual(
            status_map["/admin/debug"],
            "SHADOW_API",
        )

        self.assertEqual(
            status_map["/old-api"],
            "ZOMBIE_API",
        )

    def test_shadow_api_detection(self):

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        shadows = discovery.discover_shadow_apis(
            self.observed_routes
        )

        self.assertEqual(
            len(shadows),
            1,
        )

        self.assertEqual(
            shadows[0]["route"],
            "/admin/debug",
        )

        self.assertEqual(
            shadows[0]["status"],
            "SHADOW_API",
        )

    def test_zombie_api_detection(self):

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        zombies = discovery.discover_zombie_apis(
            self.observed_routes
        )

        self.assertEqual(
            len(zombies),
            1,
        )

        self.assertEqual(
            zombies[0]["route"],
            "/old-api",
        )

        self.assertEqual(
            zombies[0]["status"],
            "ZOMBIE_API",
        )

    def test_empty_routes(self):

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        results = discovery.discover([])

        self.assertEqual(results, [])

        def test_method_is_part_of_classification(self):
            """HTTP method must be included in runtime classification."""

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        observed_routes = [
            ("GET", "/users"),
            ("DELETE", "/users"),
        ]

        results = discovery.discover(observed_routes)

        self.assertEqual(len(results), 2)

        self.assertEqual(
            results[0]["method"],
            "GET",
        )

        self.assertEqual(
            results[0]["route"],
            "/users",
        )

        self.assertEqual(
            results[0]["status"],
            "OFFICIAL_API",
        )

        self.assertEqual(
            results[1]["method"],
            "DELETE",
        )

        self.assertEqual(
            results[1]["route"],
            "/users",
        )

        self.assertEqual(
            results[1]["status"],
            "SHADOW_API",
        )

    def test_method_matching_is_case_insensitive(self):
        """HTTP methods should be normalized to uppercase."""

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        results = discovery.discover(
            [
                ("get", "/users"),
                ("GET", "/orders"),
            ]
        )

        self.assertEqual(
            results[0]["method"],
            "GET",
        )

        self.assertEqual(
            results[0]["status"],
            "OFFICIAL_API",
        )

        self.assertEqual(
            results[1]["method"],
            "GET",
        )

        self.assertEqual(
            results[1]["status"],
            "OFFICIAL_API",
        )

    def test_method_aware_shadow_and_zombie_detection(self):
        """Method and path together determine Shadow/Zombie status."""

        discovery = LiveShadowDiscovery(
            self.official_contract
        )

        observed_routes = [
            ("GET", "/old-api"),
            ("POST", "/old-api"),
            ("GET", "/admin/debug"),
        ]

        results = discovery.discover(observed_routes)

        self.assertEqual(
            results[0]["status"],
            "ZOMBIE_API",
        )

        self.assertEqual(
            results[1]["status"],
            "SHADOW_API",
        )

        self.assertEqual(
            results[2]["status"],
            "SHADOW_API",
        )

    def test_invalid_contract(self):

        with self.assertRaises(ValueError):
            LiveShadowDiscovery(None)


if __name__ == "__main__":
    unittest.main()