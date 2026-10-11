
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


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5004")),
        debug=False,
    )
