
import csv
import json

import pytest

from src.inventory_exporter import (
    build_inventory_catalog,
    export_inventory_catalog,
)


@pytest.fixture
def sample_endpoints():
    return [
        {
            "method": "GET",
            "path": "/api/users",
            "operation_id": "getUsers",
            "summary": "Get all users",
        },
        {
            "method": "POST",
            "path": "/api/users",
            "operation_id": "createUser",
            "summary": "Create a user",
        },
    ]


@pytest.fixture
def approved_apis():
    return {
        ("GET", "/api/users"),
    }


@pytest.fixture
def runtime_events():
    return [
        {"method": "GET", "path": "/api/users"},
        {"method": "GET", "path": "/api/users"},
        {"method": "DELETE", "path": "/api/legacy"},
    ]


def test_build_inventory_catalog(
    sample_endpoints,
    approved_apis,
    runtime_events,
):
    catalog = build_inventory_catalog(
        endpoints=sample_endpoints,
        approved_apis=approved_apis,
        runtime_events=runtime_events,
        api_name="Test API",
        openapi_version="3.0.3",
    )

    assert catalog["api_name"] == "Test API"
    assert catalog["openapi_version"] == "3.0.3"
    assert catalog["total_endpoints"] == 3
    assert catalog["total_runtime_observations"] == 3


def test_approved_endpoint_is_classified(
    sample_endpoints,
    approved_apis,
):
    catalog = build_inventory_catalog(
        sample_endpoints,
        approved_apis,
    )

    endpoint = next(
        item for item in catalog["endpoints"]
        if item["method"] == "GET"
    )

    assert endpoint["discovery_state"] == "APPROVED"
    assert endpoint["is_approved"] is True


def test_unapproved_declared_endpoint_is_classified(
    sample_endpoints,
    approved_apis,
):
    catalog = build_inventory_catalog(
        sample_endpoints,
        approved_apis,
    )

    endpoint = next(
        item for item in catalog["endpoints"]
        if item["method"] == "POST"
    )

    assert endpoint["discovery_state"] == "UNAPPROVED"
    assert endpoint["is_declared"] is True


def test_runtime_only_endpoint_is_shadow(
    approved_apis,
    runtime_events,
):
    catalog = build_inventory_catalog(
        endpoints=[],
        approved_apis=approved_apis,
        runtime_events=runtime_events,
    )

    endpoint = next(
        item for item in catalog["endpoints"]
        if item["path"] == "/api/legacy"
    )

    assert endpoint["discovery_state"] == "SHADOW_API"
    assert endpoint["is_declared"] is False


def test_runtime_observations_are_counted(
    sample_endpoints,
    approved_apis,
    runtime_events,
):
    catalog = build_inventory_catalog(
        sample_endpoints,
        approved_apis,
        runtime_events,
    )

    endpoint = next(
        item for item in catalog["endpoints"]
        if item["method"] == "GET"
    )

    assert endpoint["runtime_observation_count"] == 2


def test_empty_inventory():
    catalog = build_inventory_catalog(
        endpoints=[],
        approved_apis=set(),
        runtime_events=[],
    )

    assert catalog["total_endpoints"] == 0
    assert catalog["endpoints"] == []


def test_invalid_endpoints():
    with pytest.raises(ValueError):
        build_inventory_catalog(
            endpoints="invalid",
            approved_apis=set(),
        )


def test_invalid_approved_inventory():
    with pytest.raises(ValueError):
        build_inventory_catalog(
            endpoints=[],
            approved_apis=[],
        )


def test_json_and_csv_export(
    sample_endpoints,
    approved_apis,
    runtime_events,
    tmp_path,
):
    catalog = build_inventory_catalog(
        sample_endpoints,
        approved_apis,
        runtime_events,
    )

    json_path = tmp_path / "inventory.json"
    csv_path = tmp_path / "inventory.csv"

    saved_json, saved_csv = export_inventory_catalog(
        catalog,
        json_path,
        csv_path,
    )

    assert json_path.is_file()
    assert csv_path.is_file()

    with open(saved_json, encoding="utf-8") as file:
        json_data = json.load(file)

    assert json_data["total_endpoints"] == 3

    with open(
        saved_csv,
        encoding="utf-8-sig",
        newline="",
    ) as file:
        csv_data = list(csv.DictReader(file))

    assert len(csv_data) == 3
    assert "discovery_state" in csv_data[0]


def test_export_creates_missing_directories(
    tmp_path,
):
    catalog = build_inventory_catalog(
        endpoints=[],
        approved_apis=set(),
    )

    json_path = tmp_path / "nested" / "inventory.json"
    csv_path = tmp_path / "nested" / "inventory.csv"

    export_inventory_catalog(
        catalog,
        json_path,
        csv_path,
    )

    assert json_path.is_file()
    assert csv_path.is_file()
