"""Shared database schema initialization and additive index upgrades."""

from sqlalchemy.engine import Connection

from app.database import Base
from app.models import SecurityIncident


_REQUIRED_INCIDENT_INDEXES = (
    "ix_incident_severity_detected_at",
    "ix_incident_status_detected_at",
)


def initialize_database_schema(connection: Connection) -> None:
    """Create missing tables and ensure required incident indexes exist.

    ``create_all`` creates indexes when it creates a new table, but it does
    not upgrade indexes on an existing table. The explicit, idempotent
    ``Index.create(checkfirst=True)`` calls handle that existing-database case.
    """
    Base.metadata.create_all(bind=connection)

    indexes_by_name = {
        index.name: index
        for index in SecurityIncident.__table__.indexes
    }

    for name in _REQUIRED_INCIDENT_INDEXES:
        index = indexes_by_name.get(name)
        if index is None:
            raise RuntimeError(
                f"Required database index is missing from model metadata: {name}"
            )
        index.create(bind=connection, checkfirst=True)
