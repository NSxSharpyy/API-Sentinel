from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas import SecurityIncidentSchema


def test_schema_maps_database_id_to_canonical_incident_id():
    detected_at = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    record = SimpleNamespace(
        id=17,
        detected_at=detected_at,
        severity="high",
        title="Potential BOLA",
        description="Lab heuristic detected cross-user access",
        source_ip="192.0.2.10",
        transaction_id=42,
        endpoint_id=None,
        status="open",
    )

    incident = SecurityIncidentSchema.from_model(record)
    payload = incident.model_dump(mode="json")

    assert incident.incident_id == 17
    assert "id" not in payload
    assert payload["incident_id"] == 17
    assert payload["detected_at"] == "2026-10-24T12:00:00Z"
    assert payload["endpoint_id"] is None
    assert set(payload) == set(SecurityIncidentSchema.model_fields)


def test_schema_rejects_invalid_incident_ids_and_empty_titles():
    values = {
        "incident_id": 1,
        "detected_at": datetime.now(timezone.utc),
        "severity": "high",
        "title": "Potential BOLA",
    }

    with pytest.raises(ValidationError):
        SecurityIncidentSchema(**{**values, "incident_id": 0})

    with pytest.raises(ValidationError):
        SecurityIncidentSchema(**{**values, "title": ""})
