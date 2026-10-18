
"""MOCK Billing Service: intentionally vulnerable BOLA training endpoint.

LOCAL LAB ONLY. Never deploy this service outside the isolated test environment.
"""
import os

from flask import g, jsonify

from mock_data import get_invoice, list_invoices_for_user
from security import require_auth
from service_base import create_service

app, logger = create_service("billing-service")


@app.get("/api/v2/billing/invoices")
@require_auth
def list_my_invoices():
    return jsonify(invoices=list_invoices_for_user(g.user_id))


@app.get("/api/v2/billing/invoices/<int:invoice_id>")
@require_auth
def get_invoice_by_id(invoice_id):
    invoice = get_invoice(invoice_id)

    if invoice is None:
        return jsonify(error="not_found"), 404

    # INTENTIONAL BOLA: no comparison between invoice owner and g.user_id.
    logger.info("invoice accessed", extra={"fields": {
        "invoice_id": invoice_id,
        "owner_id": invoice["owner_id"],
        "requester_id": g.user_id,
        "cross_user_access": invoice["owner_id"] != g.user_id,
    }})

    return jsonify(invoice)



# Day 16 compatibility route: authenticated but intentionally missing
# object-level authorization. LOCAL LAB ONLY.
@app.get("/api/v1/billing/<int:billing_id>")
@require_auth
def get_billing_by_id(billing_id):
    # Authentication is required by the decorator; ownership is not checked.
    record = get_invoice(billing_id)
    if record is None:
        return jsonify(error="not_found"), 404

    logger.warning(
        "INTENTIONAL BOLA accessed",
        extra={"fields": {
            "endpoint": "/api/v1/billing/<billing_id>",
            "billing_id": billing_id,
            "requester_id": g.user_id,
            "owner_id": record["owner_id"],
            "cross_user_access": record["owner_id"] != g.user_id,
        }},
    )
    return jsonify(record)


# Day 10 SHADOW API: unauthenticated, lab-only cache-reset simulation.
_cache_reset_count = 0


@app.post("/_admin/reset-cache")
def admin_reset_cache():
    global _cache_reset_count
    _cache_reset_count += 1
    logger.warning(
        "SHADOW API accessed",
        extra={"fields": {
            "endpoint": "/_admin/reset-cache",
            "reset_count": _cache_reset_count,
        }},
    )
    return jsonify(status="cache reset", reset_count=_cache_reset_count)


# Day 10 ZOMBIE API: legacy invoice lookup without authentication.
@app.get("/api/v1/invoices/<int:invoice_id>")
def v1_get_invoice(invoice_id):
    logger.warning(
        "ZOMBIE API accessed",
        extra={"fields": {
            "endpoint": "/api/v1/invoices/<id>",
            "invoice_id": invoice_id,
            "auth_required": False,
        }},
    )
    invoice = get_invoice(invoice_id)
    if invoice is None:
        return jsonify(error="not_found"), 404
    return jsonify(invoice)


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5004")),
        debug=False,
    )
