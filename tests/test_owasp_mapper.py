
import unittest
import json
import tempfile
from pathlib import Path

from src.owasp_mapper import (
    map_owasp_api9_findings,
    save_owasp_api9_report,
)


class TestOWASPAPI9Mapper(unittest.TestCase):

    def test_shadow_api_is_mapped_to_api9(self):
        findings = [
            {
                "method": "GET",
                "route": "/api/v1/internal",
                "status": "shadow",
                "finding": "Shadow API",
                "reason": "Missing from official contract.",
            }
        ]

        result = map_owasp_api9_findings(findings)

        self.assertEqual(result["total_findings"], 1)
        self.assertEqual(
            result["findings"][0]["owasp_category"],
            "API9:2023",
        )

    def test_zombie_api_is_mapped_to_api9(self):
        findings = [
            {
                "method": "GET",
                "route": "/api/v1/legacy",
                "status": "ZOMBIE_API",
                "reason": "Deprecated endpoint still receives traffic.",
            }
        ]

        result = map_owasp_api9_findings(findings)

        self.assertEqual(result["total_findings"], 1)
        self.assertEqual(
            result["findings"][0]["owasp_name"],
            "Improper Inventory Management",
        )

    def test_official_api_is_not_mapped(self):
        findings = [
            {
                "method": "GET",
                "route": "/api/v1/users",
                "status": "OFFICIAL_API",
            }
        ]

        result = map_owasp_api9_findings(findings)

        self.assertEqual(result["total_findings"], 0)

    def test_empty_findings(self):
        result = map_owasp_api9_findings([])

        self.assertEqual(result["total_findings"], 0)
        self.assertEqual(result["findings"], [])

    def test_original_finding_fields_are_preserved(self):
        finding = {
            "method": "POST",
            "route": "/api/v1/internal",
            "status": "shadow",
            "finding": "Shadow API",
            "reason": "Undocumented endpoint.",
        }

        result = map_owasp_api9_findings([finding])

        mapped = result["findings"][0]

        self.assertEqual(mapped["method"], "POST")
        self.assertEqual(mapped["route"], "/api/v1/internal")
        self.assertEqual(mapped["reason"], "Undocumented endpoint.")

    def test_none_input_is_rejected(self):
        with self.assertRaises(ValueError):
            map_owasp_api9_findings(None)

    def test_shadow_and_zombie_counts(self):
        findings = [
            {
                "method": "GET",
                "route": "/api/v1/users",
                "status": "shadow",
            },
            {
                "method": "POST",
                "route": "/api/v1/orders",
                "status": "ZOMBIE_API",
            },
        ]

        result = map_owasp_api9_findings(findings)

        self.assertEqual(result["shadow_findings"], 1)
        self.assertEqual(result["zombie_findings"], 1)

    def test_duplicate_observations_count_as_one_unique_endpoint(self):
        findings = [
            {
                "method": "GET",
                "route": "/api/v1/legacy",
                "status": "ZOMBIE_API",
            },
            {
                "method": "GET",
                "route": "/api/v1/legacy",
                "status": "ZOMBIE_API",
            },
        ]

        result = map_owasp_api9_findings(findings)

        self.assertEqual(result["total_findings"], 2)
        self.assertEqual(result["unique_endpoints"], 1)

    def test_method_is_normalized_for_unique_endpoint_count(self):
        findings = [
            {
                "method": "get",
                "route": "/api/v1/users",
                "status": "shadow",
            },
            {
                "method": "GET",
                "route": "/api/v1/users",
                "status": "shadow",
            },
        ]

        result = map_owasp_api9_findings(findings)

        self.assertEqual(result["unique_endpoints"], 1)

    def test_report_is_saved_as_json(self):
        report = map_owasp_api9_findings([
            {
                "method": "GET",
                "route": "/api/v1/legacy",
                "status": "ZOMBIE_API",
            }
        ])

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "owasp_report.json"

            saved_path = save_owasp_api9_report(
                report,
                str(output_path),
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(saved_path, str(output_path))

            with output_path.open("r", encoding="utf-8") as file:
                saved_report = json.load(file)

            self.assertEqual(saved_report["total_findings"], 1)
            self.assertEqual(
                saved_report["owasp_category"],
                "API9:2023",
            )
            self.assertIn("generated_at", saved_report)


if __name__ == "__main__":
    unittest.main()
