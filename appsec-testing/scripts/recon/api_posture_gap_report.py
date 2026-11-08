#!/usr/bin/env python3
"""Generate the API Posture Gap Report for the API-Sentinel lab."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DISCOVERY_REPORT = ROOT / "logs" / "discovery_report.json"
DEFAULT_VERIFICATION_REPORT = (
    ROOT / "logs" / "discovery_verification_report.json"
)
DEFAULT_OUTPUT_REPORT = ROOT / "logs" / "api_posture_gap_report.json"


def load_json_report(path):
    """Load a JSON report from disk."""
    if not path.is_file():
        raise FileNotFoundError(f"Report not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON report: {path}") from exc


def main():
    parser = argparse.ArgumentParser(
        description="Generate the API Posture Gap Report."
    )

    parser.add_argument(
        "--discovery-report",
        type=Path,
        default=DEFAULT_DISCOVERY_REPORT,
    )
    parser.add_argument(
        "--verification-report",
        type=Path,
        default=DEFAULT_VERIFICATION_REPORT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_REPORT,
    )

    args = parser.parse_args()

    print("API-Sentinel API Posture Gap Report")
    print("=" * 40)

    discovery_report = load_json_report(args.discovery_report)
    verification_report = load_json_report(
        args.verification_report
    )

    print("Discovery report loaded.")
    print("Verification report loaded.")

    discovered_total = discovery_report.get("total_discovered", 0)

    by_service = discovery_report.get("by_service", {})
    endpoint_classification = discovery_report.get(
        "endpoint_classification", {}
    )

    shadow_endpoints = []
    zombie_endpoints = []
    undocumented_endpoints = []

    for service, paths in endpoint_classification.items():
        for path, classification in paths.items():
            endpoint = {
                "service": service,
                "path": path,
                "classification": classification,
            }

            if classification == "shadow_candidate":
                shadow_endpoints.append(endpoint)

            elif classification == "zombie_candidate":
                zombie_endpoints.append(endpoint)

            elif classification == "versioned_undocumented_candidate":
                undocumented_endpoints.append(endpoint)

    gap_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_type": "API Posture Gap Report",
        "total_discovered_endpoints": discovered_total,
        "service_count": len(by_service),
        "shadow_candidate_count": len(shadow_endpoints),
        "zombie_candidate_count": len(zombie_endpoints),
        "undocumented_candidate_count": len(
            undocumented_endpoints
        ),
        "shadow_candidates": shadow_endpoints,
        "zombie_candidates": zombie_endpoints,
        "undocumented_candidates": undocumented_endpoints,
        "verification_summary": {
            "verdict": verification_report.get("verdict"),
            "recall": verification_report.get("recall"),
            "precision": verification_report.get("precision"),
            "missed_endpoints": verification_report.get(
                "missed_endpoints", []
            ),
            "false_positives": verification_report.get(
                "false_positives", []
            ),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(
        json.dumps(gap_report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Total discovered endpoints: {discovered_total}")
    print(f"Shadow candidates: {len(shadow_endpoints)}")
    print(f"Zombie candidates: {len(zombie_endpoints)}")
    print(
        "Undocumented candidates: "
        f"{len(undocumented_endpoints)}"
    )
    print(f"Report generated: {args.output}")

if __name__ == "__main__":
    main()