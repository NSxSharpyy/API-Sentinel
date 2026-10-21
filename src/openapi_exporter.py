import json


class OpenAPIExporter:
    """Export discovered API routes into an OpenAPI specification."""

    def __init__(
        self,
        title="API-Sentinel Generated API",
        version="1.0.0",
    ):
        self.title = title
        self.version = version

    def export(self, routes):
        """Build an OpenAPI specification from discovered routes."""

        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": self.title,
                "version": self.version,
            },
            "paths": {},
        }

        for route in routes:
            method = route.get("method", "").strip().lower()
            path = route.get("route", "").strip()

            if not method or not path:
                continue

            if not path.startswith("/"):
                path = "/" + path

            if path not in spec["paths"]:
                spec["paths"][path] = {}

            spec["paths"][path][method] = {
                "responses": {
                    "200": {
                        "description": "Successful response"
                    }
                }
            }

        return spec

    def export_json(self, routes, output_file):
        """Export routes directly to an OpenAPI JSON file."""

        spec = self.export(routes)

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(spec, file, indent=2)

        return spec