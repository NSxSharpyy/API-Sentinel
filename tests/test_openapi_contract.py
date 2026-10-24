from app.main import app


def test_openapi_documents_required_api_v1_routes():
    schema = app.openapi()
    paths = schema["paths"]

    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "API-Sentinel Backend"

    required = {
        "/api/v1/endpoints": {"limit", "offset"},
        "/api/v1/alerts": {"limit", "offset", "severity", "status"},
        "/api/v1/metrics": set(),
    }

    for path, expected_parameters in required.items():
        assert "get" in paths[path]
        parameters = paths[path]["get"].get("parameters", [])
        names = {parameter["name"] for parameter in parameters}
        assert expected_parameters <= names
