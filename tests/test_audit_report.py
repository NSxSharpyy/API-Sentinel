import json
import os
import tempfile
import unittest

from src.audit_report import SchemaAuditReport
from src.contract_differ import ContractDiffEngine


class TestSchemaAuditReport(unittest.TestCase):

    def setUp(self):
        self.diff_result = {
            "summary": {
                "official_routes": 3,
                "live_routes": 4,
                "live_only": 1,
                "official_only": 0,
                "common": 3,
                "zombie": 1,
            },
            "differences": {
                "live_only": [
                    {
                        "method": "GET",
                        "path": "/shadow-api",
                    }
                ],
                "official_only": [],
                "common": [
                    {
                        "method": "GET",
                        "path": "/users",
                    },
                    {
                        "method": "GET",
                        "path": "/orders",
                    },
                    {
                        "method": "GET",
                        "path": "/old-api",
                    },
                ],
                "zombie": [
                    {
                        "method": "GET",
                        "path": "/old-api",
                        "status": "ZOMBIE_API",
                    }
                ],
            },
        }

    def test_report_summary(self):
        report = SchemaAuditReport(
            self.diff_result
        ).generate()

        self.assertEqual(
            report["summary"]["official_routes"],
            3,
        )

        self.assertEqual(
            report["summary"]["live_routes"],
            4,
        )

        self.assertEqual(
            report["summary"]["shadow_routes"],
            1,
        )

        self.assertEqual(
            report["summary"]["zombie_routes"],
            1,
        )

    def test_shadow_api_is_present(self):
        report = SchemaAuditReport(
            self.diff_result
        ).generate()

        shadows = report["findings"]["shadow_apis"]

        self.assertEqual(
            len(shadows),
            1,
        )

        self.assertEqual(
            shadows[0]["path"],
            "/shadow-api",
        )

    def test_zombie_api_is_present(self):
        report = SchemaAuditReport(
            self.diff_result
        ).generate()

        zombies = report["findings"]["zombie_apis"]

        self.assertEqual(
            len(zombies),
            1,
        )

        self.assertEqual(
            zombies[0]["path"],
            "/old-api",
        )

    def test_invalid_diff_result(self):
        with self.assertRaises(ValueError):
            SchemaAuditReport(None)

    def test_json_export(self):
        report = SchemaAuditReport(
            self.diff_result
        )

        with tempfile.TemporaryDirectory() as temp_dir:

            output_path = os.path.join(
                temp_dir,
                "audit_report.json",
            )

            result = report.export_json(
                output_path
            )

            self.assertTrue(
                os.path.exists(result)
            )

            with open(
                result,
                "r",
                encoding="utf-8",
            ) as file:
                exported = json.load(file)

            self.assertEqual(
                exported["summary"]["shadow_routes"],
                1,
            )

    def test_real_contract_diff_integration(self):
        official_spec = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {}
                },
                "/old-api": {
                    "get": {
                        "deprecated": True
                    }
                }
            }
        }

        live_spec = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {}
                },
                "/old-api": {
                    "get": {}
                },
                "/hidden": {
                    "get": {}
                }
            }
        }

        diff = ContractDiffEngine(
            official_spec,
            live_spec,
        ).diff()

        report = SchemaAuditReport(
            diff
        ).generate()

        self.assertEqual(
            report["summary"]["shadow_routes"],
            1,
        )

        self.assertEqual(
            report["summary"]["zombie_routes"],
            1,
        )

        self.assertEqual(
            report["findings"]["shadow_apis"][0]["path"],
            "/hidden",
        )

        self.assertEqual(
            report["findings"]["zombie_apis"][0]["path"],
            "/old-api",
        )

        def test_report_type(self):
            report = SchemaAuditReport(
            self.diff_result
        ).generate()

        self.assertEqual(
            report["report_type"],
            "schema_discrepancy_audit",
        )

    def test_generated_at_exists(self):
        report = SchemaAuditReport(
            self.diff_result
        ).generate()

        self.assertIn(
            "generated_at",
            report,
        )

        self.assertTrue(
            report["generated_at"]
        )

    def test_empty_differences(self):
        diff_result = {
            "summary": {
                "official_routes": 0,
                "live_routes": 0,
            },
            "differences": {},
        }

        report = SchemaAuditReport(
            diff_result
        ).generate()

        self.assertEqual(
            report["summary"]["official_routes"],
            0,
        )

        self.assertEqual(
            report["summary"]["live_routes"],
            0,
        )

        self.assertEqual(
            report["summary"]["common_routes"],
            0,
        )

        self.assertEqual(
            report["summary"]["shadow_routes"],
            0,
        )

        self.assertEqual(
            report["summary"]["zombie_routes"],
            0,
        )

        self.assertEqual(
            report["summary"]["missing_live_routes"],
            0,
        )

        self.assertEqual(
            report["findings"]["shadow_apis"],
            [],
        )

        self.assertEqual(
            report["findings"]["zombie_apis"],
            [],
        )

if __name__ == "__main__":
    unittest.main()