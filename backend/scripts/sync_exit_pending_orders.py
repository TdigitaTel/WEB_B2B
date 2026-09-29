from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.exit_db import fetch_pending_exit_orders
from app.exit_orders import import_exit_batch
from app.models import User


def main():
    records = fetch_pending_exit_orders(1000)
    with SessionLocal() as db:
        integration_user = db.scalar(select(User).where(User.role == "ADMIN", User.active.is_(True)).order_by(User.id))
        if not integration_user:
            raise SystemExit("No existe un usuario ADMIN activo para registrar la integración")
        imported = import_exit_batch(db, records, integration_user, datetime.now(timezone.utc).isoformat())
    print({"status": "ok", "imported_or_updated": imported,
           "kardex_lines": sum(1 for order in records for line in order.lines if line.fulfillment_zone == "KARDEX"),
           "sga_lines": sum(1 for order in records for line in order.lines if line.fulfillment_zone == "SGA")})


if __name__ == "__main__":
    main()
