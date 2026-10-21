import unittest

from src.contract_differ import compare_route_to_contract


class TestPhase2Freeze(unittest.TestCase):
    """Final Phase 2 validation for Shadow and Zombie API detection."""

    def setUp(self):
        # MOCK DATA — TEMPORARY
        # This represents the official API contract.
        self.official_contract = {
            "openapi": "3.0.0",
            "info": {
                "title": "Mock API",
                "version": "1.0.0",
            },
            "paths": {
                "/api/v1/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Successful response"
                            }
                        }
                    }
                },
                "/api/v1/orders": {
                    "get": {
                        "deprecated": True,
                        "responses": {
                            "200": {
                                "description": "Deprecated endpoint"
                            }
                        }
                    }
                },
            },
        }

    def test_official_endpoint_is_not_shadow(self):
        """An endpoint present in the contract must not be flagged as Shadow."""

        result = compare_route_to_contract(
            "/api/v1/users",
            self.official_contract,
        )

        self.assertEqual(result, "OFFICIAL_API")

    def test_undocumented_endpoint_is_shadow(self):
        """An observed endpoint missing from the contract must be Shadow."""

        result = compare_route_to_contract(
            "/api/v1/admin/debug",
            self.official_contract,
        )

        self.assertEqual(result, "SHADOW_API")

    def test_deprecated_endpoint_is_zombie(self):
        """A deprecated endpoint receiving traffic must be Zombie."""

        result = compare_route_to_contract(
            "/api/v1/orders",
            self.official_contract,
        )

        self.assertEqual(result, "ZOMBIE_API")


if __name__ == "__main__":
    unittest.main()