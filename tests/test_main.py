import json
import tempfile
import unittest
from pathlib import Path

import yaml

from src.main import parse_openapi_spec


class TestParseOpenAPISpec(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)

    def write_json(self, data, filename="spec.json"):
        path = self.temp_path / filename
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def write_yaml(self, data, filename="spec.yaml"):
        path = self.temp_path / filename
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    def valid_spec(self):
        return {
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "get": {
                        "summary": "List users"
                    }
                }
            }
        }

    def test_valid_json_specification(self):
        path = self.write_json(self.valid_spec())

        result = parse_openapi_spec(str(path))

        self.assertEqual(result["openapi"], "3.0.3")
        self.assertIn("/users", result["paths"])

    def test_valid_yaml_specification(self):
        path = self.write_yaml(self.valid_spec())

        result = parse_openapi_spec(str(path))

        self.assertEqual(result["info"]["title"], "Test API")
        self.assertIn("/users", result["paths"])

    def test_missing_paths_is_rejected(self):
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            }
        }
        path = self.write_json(spec)

        with self.assertRaisesRegex(ValueError, "paths"):
            parse_openapi_spec(str(path))

    def test_invalid_json_is_rejected(self):
        path = self.temp_path / "invalid.json"
        path.write_text("{invalid json", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid JSON or YAML"):
            parse_openapi_spec(str(path))

    def test_unsupported_extension_is_rejected(self):
        path = self.temp_path / "spec.txt"
        path.write_text("test", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Unsupported"):
            parse_openapi_spec(str(path))


if __name__ == "__main__":
    unittest.main()