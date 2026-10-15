import unittest

from src.schema_generator import (
    infer_schema,
    generate_openapi_spec,
)


class TestSchemaGenerator(unittest.TestCase):

    def test_string_schema(self):
        result = infer_schema("Shirish")

        self.assertEqual(result["type"], "string")

    def test_integer_schema(self):
        result = infer_schema(25)

        self.assertEqual(result["type"], "integer")

    def test_boolean_schema(self):
        result = infer_schema(True)

        self.assertEqual(result["type"], "boolean")

    def test_float_schema(self):
        result = infer_schema(99.50)

        self.assertEqual(result["type"], "number")

    def test_object_schema(self):
        result = infer_schema({
            "id": 1,
            "name": "Shirish",
        })

        self.assertEqual(result["type"], "object")
        self.assertIn("id", result["properties"])
        self.assertIn("name", result["properties"])

    def test_array_schema(self):
        result = infer_schema([1, 2, 3])

        self.assertEqual(result["type"], "array")
        self.assertEqual(
            result["items"]["type"],
            "integer",
        )

    def test_generate_openapi_spec(self):
        events = [
            {
                "method": "GET",
                "path": "/api/v1/users",
                "response": {
                    "id": 1,
                    "name": "Shirish",
                },
            }
        ]

        spec = generate_openapi_spec(events)

        self.assertEqual(spec["openapi"], "3.0.0")
        self.assertIn("/api/v1/users", spec["paths"])
        self.assertIn(
            "get",
            spec["paths"]["/api/v1/users"],
        )

    def test_invalid_method_is_ignored(self):
        events = [
            {
                "method": "INVALID",
                "path": "/api/v1/test",
                "response": {},
            }
        ]

        spec = generate_openapi_spec(events)

        self.assertEqual(spec["paths"], {})


if __name__ == "__main__":
    unittest.main()