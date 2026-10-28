"""Shared foundation for all MOCK e-commerce microservices.

Provides: JSON logging, request IDs, /health, and safe JSON error handlers.
"""
import json
import logging
import sys
import time
import uuid

from flask import Flask, g, jsonify, request

API_VERSION = "v2"


class JsonFormatter(logging.Formatter):
    """Writes each log record as one JSON line (easy for SOC tooling to parse)."""

    def __init__(self, service_name):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "service": self.service_name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload)


def _build_logger(service_name):
    logger = logging.getLogger(service_name)
    if not logger.handlers:  # avoid duplicate handlers if imported twice
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service_name))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def not_implemented(feature):
    """Standard placeholder response for routes built in later days."""
    return jsonify(error="not_implemented", detail=feature), 501


def create_service(service_name):
    app = Flask(service_name)
    logger = _build_logger(service_name)

    @app.before_request
    def start_request():
        g.start = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    @app.after_request
    def finish_request(response):
        duration_ms = round((time.perf_counter() - g.start) * 1000, 2)
        response.headers["X-Request-ID"] = g.request_id
        logger.info("request", extra={"fields": {
            "request_id": g.request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.remote_addr,
        }})
        return response

    @app.get("/health")
    def health():
        return jsonify(service=service_name, status="ok", api_version=API_VERSION)

    # Safe error handlers: JSON only, never a stack trace.
    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify(error="not_found"), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify(error="method_not_allowed"), 405

    @app.errorhandler(Exception)
    def handle_500(err):
        logger.error("unhandled exception", extra={"fields": {"type": type(err).__name__}})
        return jsonify(error="internal_server_error"), 500

    return app, logger
