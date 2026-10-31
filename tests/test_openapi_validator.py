
import unittest

from src.openapi_validator import validate_openapi_spec


class TestOpenAPIValidator(unittest.TestCase):

    def setUp(self):
        self.valid_spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0",
            },
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Successful response",
                            }
                        }
                    }
                }
            },
        }

    def test_valid_openapi_specification(self):
        result = validate_openapi_spec(self.valid_spec)

        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_missing_openapi_version(self):
        spec = self.valid_spec.copy()
        del spec["openapi"]

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_missing_info_section(self):
        spec = self.valid_spec.copy()
        del spec["info"]

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_missing_paths_section(self):
        spec = self.valid_spec.copy()
        del spec["paths"]

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_invalid_openapi_version(self):
        spec = self.valid_spec.copy()
        spec["openapi"] = "2.0.0"

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_invalid_info_section(self):
        spec = self.valid_spec.copy()
        spec["info"] = "invalid"

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_invalid_paths_section(self):
        spec = self.valid_spec.copy()
        spec["paths"] = "invalid"

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_non_dictionary_input(self):
        result = validate_openapi_spec("invalid")

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_missing_operation_responses(self):
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0",
            },
            "paths": {
                "/users": {
                    "get": {}
                }
            },
        }

        result = validate_openapi_spec(spec)

        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
