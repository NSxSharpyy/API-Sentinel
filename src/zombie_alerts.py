
"""
Zombie API traffic alert engine for API-Sentinel.

Converts ZombieAPIDetector findings into structured operator alerts.
Repeated observations of the same method/route are aggregated.
"""

from __future__ import annotations

import json
import uuid

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def generate_zombie_alerts(
    findings: list[dict[str, Any]],
    detected_at: str | None = None,
) -> dict[str, Any]:
    """
    Convert Zombie API findings into operator alerts.

    Findings with the same HTTP method and route are aggregated
    into one alert with an occurrence count.
    """

    if not isinstance(findings, list):
        raise ValueError("Zombie findings must be a list.")

    timestamp = detected_at or datetime.now(
        timezone.utc
    ).isoformat()

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        method = finding.get("method")
        route = finding.get("route")

        if not isinstance(method, str) or not isinstance(route, str):
            continue

        method = method.strip().upper()
        route = route.strip()

        if not method or not route:
            continue

        grouped[(method, route)].append(finding)

    alerts = []

    for (method, route), observations in sorted(grouped.items()):

        reasons = sorted({
            reason
            for item in observations
            if isinstance(
                (reason := item.get("reason")),
                str,
            )
        })

        alerts.append({
            "alert_id": str(uuid.uuid4()),
            "alert_type": "ZOMBIE_API_TRAFFIC",
            "severity": "HIGH",
            "status": "OPEN",
            "method": method,
            "route": route,
            "endpoint_status": "ZOMBIE_API",
            "reasons": reasons,
            "message": (
                f"Live traffic detected on zombie API endpoint: "
                f"{method} {route}"
            ),
            "occurrence_count": len(observations),
            "first_seen": timestamp,
            "last_seen": timestamp,
            "detected_at": timestamp,
            "needs_review": True,
        })

    return {
        "generated_at": timestamp,
        "total_alerts": len(alerts),
        "total_observations": sum(
            alert["occurrence_count"] for alert in alerts
        ),
        "alerts": alerts,
    }


def save_zombie_alerts(
    report: dict[str, Any],
    output_path: str | Path = "reports/zombie_alerts.json",
) -> str:
    """Save the Zombie API alert report as JSON."""

    if not isinstance(report, dict):
        raise ValueError("Alert report must be a dictionary.")

    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False,
        )

    return str(report_path)
