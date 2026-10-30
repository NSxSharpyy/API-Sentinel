
"""Tests for API-Sentinel parameter drift detection."""

import pytest

from src.parameter_drift import (
    detect_parameter_drift,
    find_undocumented_fields,
    match_operation,
)


@pytest.fixture
def official_spec():
    """Provide a representative official OpenAPI contract."""

    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Test API",
            "version": "1.0.0",
        },
        "paths": {
            "/users/{userId}": {
                "put": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string"
                                        },
                                        "email": {
                                            "type": "string"
                                        },
                                        "profile": {
                                            "type": "object",
                                            "properties": {
                                                "city": {
                                                    "type": "string"
                                                }
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {
                                                "type": "integer"
                                            },
                                            "name": {
                                                "type": "string"
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def test_match_operation_with_path_parameter(official_spec):
    """OpenAPI route parameters should match concrete runtime paths."""

    operation = match_operation(
        "PUT",
        "/users/123",
        official_spec,
    )

    assert operation is not None
    assert "requestBody" in operation


def test_unmatched_endpoint_returns_none(official_spec):
    """Unknown routes must not match an official operation."""

    operation = match_operation(
        "GET",
        "/admin/users",
        official_spec,
    )

    assert operation is None


def test_detect_undocumented_request_field(official_spec):
    """Additional request fields should be reported."""

    events = [
        {
            "method": "PUT",
            "path": "/users/123",
            "request": {
                "name": "John",
                "email": "john@example.com",
                "admin_override": True,
            },
        }
    ]

    report = detect_parameter_drift(
        official_spec,
        events,
    )

    assert report["summary"]["total_drift_findings"] == 1
    assert report["summary"]["undocumented_request_fields"] == 1

    finding = report["findings"][0]

    assert finding["field"] == "admin_override"
    assert finding["location"] == "request"
    assert finding["drift_type"] == "undocumented_field"
    assert finding["status"] == "needs_review"


def test_detect_undocumented_response_field(official_spec):
    """Additional response fields should be reported."""

    events = [
        {
            "method": "PUT",
            "path": "/users/123",
            "response": {
                "id": 123,
                "name": "John",
                "internal_debug": "enabled",
            },
        }
    ]

    report = detect_parameter_drift(
        official_spec,
        events,
    )

    assert report["summary"]["total_drift_findings"] == 1
    assert report["summary"]["undocumented_response_fields"] == 1

    finding = report["findings"][0]

    assert finding["field"] == "internal_debug"
    assert finding["location"] == "response"


def test_detect_nested_undocumented_field(official_spec):
    """Undocumented nested fields should be detected."""

    events = [
        {
            "method": "PUT",
            "path": "/users/123",
            "request": {
                "name": "John",
                "email": "john@example.com",
                "profile": {
                    "city": "Pune",
                    "internal_flag": True,
                },
            },
        }
    ]

    report = detect_parameter_drift(
        official_spec,
        events,
    )

    assert report["summary"]["total_drift_findings"] == 1
    assert report["findings"][0]["field"] == (
        "profile.internal_flag"
    )


def test_missing_payload_is_not_treated_as_empty(official_spec):
    """Missing request and response payloads should be skipped."""

    events = [
        {
            "method": "PUT",
            "path": "/users/123",
        }
    ]

    report = detect_parameter_drift(
        official_spec,
        events,
    )

    assert report["summary"]["total_runtime_events_checked"] == 1
    assert report["summary"]["total_drift_findings"] == 0


def test_unknown_endpoint_is_not_checked(official_spec):
    """Drift detection should only inspect official endpoints."""

    events = [
        {
            "method": "POST",
            "path": "/shadow/users",
            "request": {
                "secret_field": "value",
            },
        }
    ]

    report = detect_parameter_drift(
        official_spec,
        events,
    )

    assert report["summary"]["total_runtime_events_checked"] == 0
    assert report["summary"]["total_drift_findings"] == 0


def test_local_schema_reference_is_resolved():
    """Local OpenAPI component references should be supported."""

    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Reference API",
            "version": "1.0.0",
        },
        "paths": {
            "/accounts": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/Account"
                                }
                            }
                        }
                    },
                    "responses": {},
                }
            }
        },
        "components": {
            "schemas": {
                "Account": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string"
                        }
                    },
                }
            }
        },
    }

    events = [
        {
            "method": "POST",
            "path": "/accounts",
            "request": {
                "username": "john",
                "unexpected": True,
            },
        }
    ]

    report = detect_parameter_drift(
        spec,
        events,
    )

    assert report["summary"]["total_drift_findings"] == 1
    assert report["findings"][0]["field"] == "unexpected"


def test_known_fields_do_not_create_findings(official_spec):
    """Documented request and response fields should pass."""

    events = [
        {
            "method": "PUT",
            "path": "/users/123",
            "request": {
                "name": "John",
                "email": "john@example.com",
                "profile": {
                    "city": "Pune",
                },
            },
            "response": {
                "id": 123,
                "name": "John",
            },
        }
    ]

    report = detect_parameter_drift(
        official_spec,
        events,
    )

    assert report["summary"]["total_runtime_events_checked"] == 1
    assert report["summary"]["total_drift_findings"] == 0
    assert report["findings"] == []


def test_find_undocumented_fields_directly(official_spec):
    """The recursive field comparison should work independently."""

    observed = {
        "name": "John",
        "profile": {
            "city": "Pune",
            "secret": True,
        },
    }

    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string"
            },
            "profile": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string"
                    }
                },
            },
        },
    }

    findings = find_undocumented_fields(
        observed,
        schema,
        official_spec,
        "request",
    )

    assert len(findings) == 1
    assert findings[0]["field"] == "profile.secret"
