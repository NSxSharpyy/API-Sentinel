import unittest

from src.runtime import (
    build_approved_endpoints,
    find_unapproved_endpoints,
)


class TestRuntimeEngine(unittest.TestCase):

    def setUp(self):
        self.spec = {
            "paths": {
                "/users": {
                    "get": {
                        "summary": "Get users"
                    }
                },
                "/users/{id}": {
                    "get": {
                        "summary": "Get user by ID"
                    }
                }
            }
        }

        self.approved = build_approved_endpoints(self.spec)

    def test_approved_endpoint_is_not_flagged(self):
        events = [
            {"method": "GET", "path": "/users"}
        ]

        findings = find_unapproved_endpoints(
            events,
            self.approved
        )

        self.assertEqual(findings, [])

    def test_unapproved_endpoint_is_flagged(self):
        events = [
            {"method": "DELETE", "path": "/users/42"}
        ]

        findings = find_unapproved_endpoints(
            events,
            self.approved
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["method"], "DELETE")

    def test_openapi_path_parameter_matches(self):
        events = [
            {"method": "GET", "path": "/users/123"}
        ]

        findings = find_unapproved_endpoints(
            events,
            self.approved
        )

        self.assertEqual(findings, [])

    def test_unapproved_path_is_flagged(self):
        events = [
            {"method": "GET", "path": "/internal/debug"}
        ]

        findings = find_unapproved_endpoints(
            events,
            self.approved
        )

        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()