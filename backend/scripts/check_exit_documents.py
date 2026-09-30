import sys

from app.erp_db import fetch_customer_delivery_notes, fetch_customer_invoices


def main() -> None:
    customer_code = (sys.argv[1] if len(sys.argv) > 1 else "00004").strip()
    delivery_notes = fetch_customer_delivery_notes(customer_code, 3)
    invoices = fetch_customer_invoices(customer_code, 3)
    print({
        "status": "ok",
        "customer_code": customer_code,
        "delivery_notes": delivery_notes,
        "invoices": invoices,
    })


if __name__ == "__main__":
    main()
