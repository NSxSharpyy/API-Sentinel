import unittest

from src.zombie_detector import ZombieAPIDetector


class TestZombieAPIDetector(unittest.TestCase):

    def test_flags_deprecated_endpoint(self):
        official_contract = {
            "paths": {
                "/api/v1/old-users": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/old-users"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["method"],
            "GET"
        )
        self.assertEqual(
            findings[0]["route"],
            "/api/v1/old-users"
        )
        self.assertEqual(
            findings[0]["status"],
            "ZOMBIE_API"
        )

    def test_flags_deprecated_parameterized_endpoint(self):
        official_contract = {
            "paths": {
                "/api/v1/users/{id}": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/users/123"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["method"],
            "GET"
        )
        self.assertEqual(
            findings[0]["route"],
            "/api/v1/users/123"
        )
        self.assertEqual(
            findings[0]["status"],
            "ZOMBIE_API"
        )

    def test_different_method_is_not_zombie(self):
        official_contract = {
            "paths": {
                "/api/v1/users/{id}": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "DELETE",
                "route": "/api/v1/users/123"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(findings, [])

    def test_does_not_flag_active_endpoint(self):
        official_contract = {
            "paths": {
                "/api/v1/users": {
                    "get": {
                        "deprecated": False
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/users"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(findings, [])

    def test_does_not_flag_undocumented_endpoint(self):
        official_contract = {
            "paths": {
                "/api/v1/users": {
                    "get": {
                        "deprecated": False
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "POST",
                "route": "/api/v1/admin/export"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(findings, [])

    def test_flags_inactive_endpoint(self):
        official_contract = {
            "paths": {
                "/api/v1/legacy": {
                    "get": {
                        "inactive": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/legacy"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["status"],
            "ZOMBIE_API"
        )

    def test_detects_multiple_zombie_apis(self):
        official_contract = {
            "paths": {
                "/api/v1/old-users": {
                    "get": {
                        "deprecated": True
                    }
                },
                "/api/v1/legacy-orders": {
                    "post": {
                        "inactive": True
                    }
                },
                "/api/v1/users": {
                    "get": {
                        "deprecated": False
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/old-users"
            },
            {
                "method": "POST",
                "route": "/api/v1/legacy-orders"
            },
            {
                "method": "GET",
                "route": "/api/v1/users"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(len(findings), 2)

        self.assertEqual(
            findings[0]["route"],
            "/api/v1/old-users"
        )

        self.assertEqual(
            findings[1]["route"],
            "/api/v1/legacy-orders"
        )

    def test_invalid_observed_entries_are_ignored(self):
        official_contract = {
            "paths": {
                "/api/v1/legacy": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            None,
            {},
            {
                "method": "",
                "route": "/api/v1/legacy"
            },
            {
                "method": "GET",
                "route": ""
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(findings, [])

    def test_method_matching_is_case_insensitive(self):
        official_contract = {
            "paths": {
                "/api/v1/legacy": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "get",
                "route": "/api/v1/legacy"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["method"],
            "GET"
        )

    def test_deprecated_endpoint_is_not_claimed_permanently_retired(self):
        official_contract = {
            "paths": {
                "/api/v1/migration": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/migration"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        findings = detector.analyze(observed_routes)

        self.assertEqual(len(findings), 1)

        self.assertEqual(
            findings[0]["status"],
            "ZOMBIE_API"
        )

        self.assertIn(
            "deprecated",
            findings[0]["reason"]
        )

        self.assertIn(
            "still receives live traffic",
            findings[0]["reason"]
        )

        self.assertNotIn(
            "permanently retired",
            findings[0]["reason"].lower()
        )

    def test_count(self):
        official_contract = {
            "paths": {
                "/api/v1/old-one": {
                    "get": {
                        "deprecated": True
                    }
                },
                "/api/v1/old-two": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        observed_routes = [
            {
                "method": "GET",
                "route": "/api/v1/old-one"
            },
            {
                "method": "GET",
                "route": "/api/v1/old-two"
            }
        ]

        detector = ZombieAPIDetector(official_contract)

        detector.analyze(observed_routes)

        self.assertEqual(
            detector.count(),
            2
        )


if __name__ == "__main__":
    unittest.main()