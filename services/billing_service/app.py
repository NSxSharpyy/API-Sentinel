"""MOCK Billing Service. The intentional BOLA flaw is added on Day 2 (NOT today)."""
import os

from service_base import create_service, not_implemented

app, logger = create_service("billing-service")


@app.get("/api/v2/billing/invoices/<int:invoice_id>")
def get_invoice(invoice_id):
    return not_implemented("invoice lookup: implemented Day 2 (intentionally flawed)")


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5004")))
