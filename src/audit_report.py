import json
from datetime import datetime, timezone


class SchemaAuditReport:
    """Generate an audit report from API contract discrepancies."""

    def __init__(self, diff_result):
        if not isinstance(diff_result, dict):
            raise ValueError("diff_result must be a dictionary.")

        self.diff_result = diff_result

    def generate(self):
        """Build a structured schema discrepancy audit report."""

        summary = self.diff_result.get("summary", {})
        differences = self.diff_result.get("differences", {})

        live_only = differences.get("live_only", [])
        official_only = differences.get("official_only", [])
        common = differences.get("common", [])
        zombie = differences.get("zombie", [])

        return {
            "report_type": "schema_discrepancy_audit",
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),

            "summary": {
                "official_routes": summary.get(
                    "official_routes", 0
                ),
                "live_routes": summary.get(
                    "live_routes", 0
                ),
                "common_routes": len(common),
                "shadow_routes": len(live_only),
                "zombie_routes": len(zombie),
                "missing_live_routes": len(official_only),
            },

            "findings": {
                "shadow_apis": live_only,
                "zombie_apis": zombie,
                "official_only": official_only,
                "common_apis": common,
            },
        }

    def export_json(self, output_path):
        """Write the audit report to a JSON file."""

        report = self.generate()

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report,
                file,
                indent=2,
            )

        return output_path