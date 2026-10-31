
import unittest

from src.schema_generator import generate_openapi_spec
from src.openapi_exporter import OpenAPIExporter
from src.openapi_validator import validate_openapi_spec


class TestOpenAPICompliance(unittest.TestCase):

    def test_schema_generator_output_is_compliant(self):
        events = [
            {
                "method": "GET",
                "path": "/api/users",
                "response": {
                    "id": 101,
                    "name": "Test User",
                },
            }
        ]

        spec = generate_openapi_spec(events)
        result = validate_openapi_spec(spec)

        self.assertTrue(result["valid"], result["errors"])

    def test_openapi_exporter_output_is_compliant(self):
        routes = [
            {
                "method": "GET",
                "route": "/api/users",
            },
            {
                "method": "POST",
                "route": "/api/users",
            },
        ]

        spec = OpenAPIExporter().export(routes)
        result = validate_openapi_spec(spec)

        self.assertTrue(result["valid"], result["errors"])

    def test_request_and_response_schemas_are_compliant(self):
        events = [
            {
                "method": "POST",
                "path": "/api/users",
                "request": {
                    "name": "Test User",
                    "age": 21,
                },
                "response": {
                    "id": 101,
                    "active": True,
                },
            }
        ]

        spec = generate_openapi_spec(events)
        result = validate_openapi_spec(spec)

        self.assertTrue(result["valid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
