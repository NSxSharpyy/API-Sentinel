import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.repo_crawler import (
    discover_openapi_files,
    extract_api_contracts,
    save_api_contracts,
)


class TestRepositoryCrawler(unittest.TestCase):

    @patch("src.repo_crawler.urlopen")
    def test_discovers_openapi_files(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value

        mock_response.read.return_value = b'''
        {
            "truncated": false,
            "tree": [
                {"path": "specs/openapi.json", "type": "blob"},
                {"path": "docs/swagger.yaml", "type": "blob"},
                {"path": "data/example.json", "type": "blob"},
                {"path": "src/main.py", "type": "blob"}
            ]
        }
        '''

        result = discover_openapi_files("example", "test-repo")

        self.assertEqual(
            result,
            ["docs/swagger.yaml", "specs/openapi.json"],
        )

    @patch("src.repo_crawler.urlopen")
    def test_rejects_truncated_tree(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value

        mock_response.read.return_value = b'''
        {
            "truncated": true,
            "tree": []
        }
        '''

        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            discover_openapi_files("example", "test-repo")

    def test_extract_api_contracts(self):
        spec = {
            "paths": {
                "/pets/{petId}": {
                    "parameters": [
                        {
                            "name": "petId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "get": {
                        "operationId": "getPetById",
                        "summary": "Get pet by ID",
                    },
                }
            }
        }

        contracts = extract_api_contracts(spec)

        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["path"], "/pets/{petId}")
        self.assertEqual(contracts[0]["method"], "GET")
        self.assertEqual(contracts[0]["operation_id"], "getPetById")
        self.assertEqual(
            contracts[0]["parameters"][0]["name"],
            "petId",
        )

    def test_save_api_contracts(self):
        contracts = [
            {
                "path": "/pets",
                "method": "GET",
                "operation_id": "listPets",
                "summary": "List pets",
                "parameters": [],
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = str(Path(temp_dir) / "contracts.json")

            save_api_contracts(contracts, output_path)

            with open(output_path, encoding="utf-8") as file:
                saved_data = json.load(file)

            self.assertEqual(saved_data, contracts)


if __name__ == "__main__":
    unittest.main()