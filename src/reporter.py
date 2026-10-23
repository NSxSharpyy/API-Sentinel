import json
from datetime import datetime, timezone
from pathlib import Path


def save_findings(
    findings: list[dict],
    output_path: str = "reports/shadow_api_findings.json",
) -> str:
    """Save API security findings to a JSON report."""

    report_path = Path(output_path)

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_findings": len(findings),
        "findings": findings,
    }

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            indent=4,
        )

    return str(report_path)