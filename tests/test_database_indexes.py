from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.schema import CreateTable

from app.database import Base
from app.database_schema import initialize_database_schema
from app.models import SecurityIncident


EXPECTED_INDEXES = {
    "ix_incident_severity_detected_at": ["severity", "detected_at"],
    "ix_incident_status_detected_at": ["status", "detected_at"],
}


def _incident_indexes(connection):
    return {
        index["name"]: index["column_names"]
        for index in inspect(connection).get_indexes("security_incidents")
    }


def test_fresh_database_creates_query_indexes():
    engine = create_engine("sqlite:///:memory:")

    try:
        with engine.begin() as connection:
            initialize_database_schema(connection)
            indexes = _incident_indexes(connection)

        for name, columns in EXPECTED_INDEXES.items():
            assert indexes[name] == columns
    finally:
        engine.dispose()


def test_existing_database_gets_indexes_without_losing_data():
    engine = create_engine("sqlite:///:memory:")

    try:
        with engine.begin() as connection:
            # Simulate an older database: create tables without model indexes.
            for table in Base.metadata.sorted_tables:
                connection.execute(CreateTable(table))

            connection.execute(
                SecurityIncident.__table__.insert().values(
                    detected_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                    severity="high",
                    title="Existing incident",
                    status="open",
                )
            )

            # Run the additive upgrade twice to verify idempotency.
            initialize_database_schema(connection)
            initialize_database_schema(connection)

            indexes = _incident_indexes(connection)
            saved_title = connection.execute(
                select(SecurityIncident.title)
            ).scalar_one()

        for name, columns in EXPECTED_INDEXES.items():
            assert indexes[name] == columns

        assert saved_title == "Existing incident"
    finally:
        engine.dispose()


def test_filtered_alert_queries_do_not_require_temporary_sort():
    engine = create_engine("sqlite:///:memory:")

    queries = [
        (
            """
            SELECT id, detected_at, severity, status
            FROM security_incidents
            WHERE severity = 'high'
            ORDER BY detected_at DESC, id DESC
            LIMIT 50 OFFSET 0
            """
        ),
        (
            """
            SELECT id, detected_at, severity, status
            FROM security_incidents
            WHERE status = 'open'
            ORDER BY detected_at DESC, id DESC
            LIMIT 50 OFFSET 0
            """
        ),
    ]

    try:
        with engine.begin() as connection:
            initialize_database_schema(connection)

            for query in queries:
                plan = connection.exec_driver_sql(
                    "EXPLAIN QUERY PLAN " + query
                ).fetchall()
                details = [row[3] for row in plan]

                assert not any(
                    "USE TEMP B-TREE FOR ORDER BY" in detail
                    for detail in details
                ), details
    finally:
        engine.dispose()


def test_combined_alert_filters_do_not_require_temporary_sort():
    engine = create_engine("sqlite:///:memory:")

    query = """
        SELECT id, detected_at, severity, status
        FROM security_incidents
        WHERE severity = 'high' AND status = 'open'
        ORDER BY detected_at DESC, id DESC
        LIMIT 50 OFFSET 0
    """

    try:
        with engine.begin() as connection:
            initialize_database_schema(connection)

            plan = connection.exec_driver_sql(
                "EXPLAIN QUERY PLAN " + query
            ).fetchall()
            details = [row[3] for row in plan]

            assert not any(
                "USE TEMP B-TREE FOR ORDER BY" in detail
                for detail in details
            ), details
    finally:
        engine.dispose()
