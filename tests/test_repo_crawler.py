import unittest
from unittest.mock import patch

from src.repo_crawler import discover_openapi_files


class TestRepositoryCrawler(unittest.TestCase):

    @patch("src.repo_crawler.urlopen")
    def test_discovers_openapi_files(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value

        mock_response.read.return_value = b'''
        {
            "truncated": false,
            "tree": [
                {
                    "path": "specs/openapi.json",
                    "type": "blob"
                },
                {
                    "path": "docs/swagger.yaml",
                    "type": "blob"
                },
                {
                    "path": "data/example.json",
                    "type": "blob"
                },
                {
                    "path": "src/main.py",
                    "type": "blob"
                }
            ]
        }
        '''

        result = discover_openapi_files("example", "test-repo")

        self.assertEqual(
            result,
            ["docs/swagger.yaml", "specs/openapi.json"]
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


if __name__ == "__main__":
    unittest.main()