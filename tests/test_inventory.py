import unittest

from src.inventory import find_unapproved_apis


class TestInventory(unittest.TestCase):

    def setUp(self):
        self.approved = {
            ("GET", "/users"),
            ("POST", "/users"),
        }

    def test_detect_unapproved_endpoint(self):
        discovered = [
            {
                "method": "GET",
                "path": "/users",
                "summary": "List users",
            },
            {
                "method": "DELETE",
                "path": "/users/{id}",
                "summary": "Delete a user",
            },
        ]

        result = find_unapproved_apis(
            discovered,
            self.approved,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["method"],
            "DELETE",
        )
        self.assertEqual(
            result[0]["path"],
            "/users/{id}",
        )

    def test_all_endpoints_approved(self):
        discovered = [
            {
                "method": "GET",
                "path": "/users",
                "summary": "List users",
            },
        ]

        result = find_unapproved_apis(
            discovered,
            self.approved,
        )

        self.assertEqual(result, [])

    def test_empty_discovered_endpoints(self):
        result = find_unapproved_apis(
            [],
            self.approved,
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()