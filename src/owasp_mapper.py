
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OWASP_API9_CATEGORY = "API9:2023"
OWASP_API9_NAME = "Improper Inventory Management"

SHADOW_STATUSES = {
    "shadow",
    "shadow_api",
}

ZOMBIE_STATUSES = {
    "zombie_api",
}


def map_owasp_api9_findings(
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Map detected Shadow and Zombie APIs to OWASP API9:2023.

    Preserve every finding and its original fields.
    Include separate counts for observations and unique endpoints.
    """

    if findings is None:
        raise ValueError("Findings cannot be None.")

    if not isinstance(findings, list):
        raise ValueError("Findings must be a list.")

    mapped_findings = []

    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("Each finding must be a dictionary.")

        status = finding.get("status")

        if not isinstance(status, str):
            continue

        normalized_status = status.strip().lower()

        if normalized_status not in (
            SHADOW_STATUSES | ZOMBIE_STATUSES
        ):
            continue

        mapped_finding = finding.copy()

        mapped_finding.update({
            "owasp_category": OWASP_API9_CATEGORY,
            "owasp_name": OWASP_API9_NAME,
        })

        mapped_findings.append(mapped_finding)

    unique_endpoints = {
        (
            finding.get("method", "").strip().upper(),
            finding.get("route", finding.get("path", "")).strip(),
        )
        for finding in mapped_findings
        if isinstance(finding.get("method"), str)
        and isinstance(
            finding.get("route", finding.get("path", "")),
            str,
        )
    }

    shadow_count = sum(
        1
        for finding in mapped_findings
        if finding.get("status", "").strip().lower()
        in SHADOW_STATUSES
    )

    zombie_count = sum(
        1
        for finding in mapped_findings
        if finding.get("status", "").strip().lower()
        in ZOMBIE_STATUSES
    )

    return {
        "owasp_category": OWASP_API9_CATEGORY,
        "owasp_name": OWASP_API9_NAME,
        "total_findings": len(mapped_findings),
        "unique_endpoints": len(unique_endpoints),
        "shadow_findings": shadow_count,
        "zombie_findings": zombie_count,
        "findings": mapped_findings,
    }


def save_owasp_api9_report(
    report: dict[str, Any],
    output_path: str = "reports/owasp_api9_findings.json",
) -> str:
    """Save OWASP API9 mapping findings as a JSON report."""

    if not isinstance(report, dict):
        raise ValueError("Report must be a dictionary.")

    if not isinstance(report.get("findings"), list):
        raise ValueError("Report must contain a findings list.")

    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            indent=4,
            ensure_ascii=False,
        )

    return str(report_path)
