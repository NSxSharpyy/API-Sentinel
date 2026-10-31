
import json
import tempfile
import unittest
from pathlib import Path

from src.zombie_alerts import (
    generate_zombie_alerts,
    save_zombie_alerts,
)


class TestZombieAlerts(unittest.TestCase):

    def setUp(self):
        self.findings = [
            {
                "method": "GET",
                "route": "/api/v1/old-users",
                "status": "ZOMBIE_API",
                "reason": "deprecated",
            },
            {
                "method": "GET",
                "route": "/api/v1/old-users",
                "status": "ZOMBIE_API",
                "reason": "deprecated",
            },
            {
                "method": "POST",
                "route": "/api/v1/legacy-orders",
                "status": "ZOMBIE_API",
                "reason": "inactive",
            },
        ]

    def test_generates_alerts_for_zombie_findings(self):
        report = generate_zombie_alerts(
            self.findings,
            detected_at="2026-10-31T10:00:00+00:00",
        )

        self.assertEqual(report["total_alerts"], 2)
        self.assertEqual(report["total_observations"], 3)

    def test_repeated_events_are_aggregated(self):
        report = generate_zombie_alerts(self.findings)

        alert = next(
            item for item in report["alerts"]
            if item["route"] == "/api/v1/old-users"
        )

        self.assertEqual(alert["occurrence_count"], 2)

    def test_alert_has_expected_fields(self):
        report = generate_zombie_alerts(self.findings)
        alert = report["alerts"][0]

        self.assertEqual(alert["alert_type"], "ZOMBIE_API_TRAFFIC")
        self.assertEqual(alert["severity"], "HIGH")
        self.assertEqual(alert["status"], "OPEN")
        self.assertEqual(alert["endpoint_status"], "ZOMBIE_API")
        self.assertTrue(alert["needs_review"])
        self.assertIn("alert_id", alert)
        self.assertIn("detected_at", alert)

    def test_empty_findings_generate_no_alerts(self):
        report = generate_zombie_alerts([])

        self.assertEqual(report["total_alerts"], 0)
        self.assertEqual(report["alerts"], [])

    def test_invalid_findings_are_ignored(self):
        report = generate_zombie_alerts([
            None,
            {},
            {"method": "", "route": "/api/old"},
            {"method": "GET", "route": ""},
        ])

        self.assertEqual(report["total_alerts"], 0)

    def test_invalid_input_raises_error(self):
        with self.assertRaises(ValueError):
            generate_zombie_alerts(None)

    def test_report_is_saved_as_json(self):
        report = generate_zombie_alerts(self.findings)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "zombie_alerts.json"

            saved_path = save_zombie_alerts(report, output)

            self.assertTrue(Path(saved_path).exists())

            with open(saved_path, encoding="utf-8") as file:
                saved_report = json.load(file)

            self.assertEqual(saved_report["total_alerts"], 2)


if __name__ == "__main__":
    unittest.main()
