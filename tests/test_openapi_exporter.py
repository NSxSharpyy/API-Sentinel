import json
import os
import tempfile
import unittest

from src.openapi_exporter import OpenAPIExporter


class TestOpenAPIExporter(unittest.TestCase):

    def test_export_creates_openapi_document(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "GET",
                "route": "/api/users"
            }
        ]

        spec = exporter.export(routes)

        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertIn("info", spec)
        self.assertIn("paths", spec)

    def test_export_creates_route(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "GET",
                "route": "/api/users"
            }
        ]

        spec = exporter.export(routes)

        self.assertIn("/api/users", spec["paths"])
        self.assertIn("get", spec["paths"]["/api/users"])

    def test_export_supports_multiple_methods(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "GET",
                "route": "/api/users"
            },
            {
                "method": "POST",
                "route": "/api/users"
            }
        ]

        spec = exporter.export(routes)

        self.assertIn("get", spec["paths"]["/api/users"])
        self.assertIn("post", spec["paths"]["/api/users"])

    def test_export_ignores_invalid_route(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "",
                "route": "/api/users"
            },
            {
                "method": "GET",
                "route": ""
            }
        ]

        spec = exporter.export(routes)

        self.assertEqual(spec["paths"], {})

    def test_export_normalizes_missing_leading_slash(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "GET",
                "route": "api/users"
            }
        ]

        spec = exporter.export(routes)

        self.assertIn("/api/users", spec["paths"])

    def test_export_normalizes_method_case(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "get",
                "route": "/api/users"
            }
        ]

        spec = exporter.export(routes)

        self.assertIn("get", spec["paths"]["/api/users"])

    def test_export_json_creates_file(self):
        exporter = OpenAPIExporter()

        routes = [
            {
                "method": "GET",
                "route": "/api/users"
            }
        ]

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".json"
        ) as temp_file:
            output_file = temp_file.name

        try:
            exporter.export_json(routes, output_file)

            self.assertTrue(os.path.exists(output_file))

            with open(output_file, "r", encoding="utf-8") as file:
                data = json.load(file)

            self.assertEqual(data["openapi"], "3.0.3")
            self.assertIn("/api/users", data["paths"])

        finally:
            if os.path.exists(output_file):
                os.remove(output_file)


if __name__ == "__main__":
    unittest.main()