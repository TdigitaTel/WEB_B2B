import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.config import settings
from app.db import SessionLocal
from app.exit_db import fetch_pending_exit_orders
from app.exit_orders import import_exit_batch
from app.models import IntegrationCursor, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("exit-order-sync")
LOCK_ID = 6006091


def sync_once() -> int:
    with SessionLocal() as db:
        locked = bool(db.scalar(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": LOCK_ID}))
        if not locked:
            logger.info("Otra sincronización está en curso; se omite este ciclo")
            return 0
        try:
            integration_user = db.scalar(select(User).where(User.role == "ADMIN", User.active.is_(True)).order_by(User.id))
            if not integration_user:
                raise RuntimeError("No existe un usuario ADMIN activo para registrar la integración")
            records = fetch_pending_exit_orders(settings.exit_order_sync_batch_size)
            imported = import_exit_batch(db, records, integration_user, datetime.now(timezone.utc).isoformat())
            logger.info("Sincronización completada: %s pedidos leídos", imported)
            return imported
        except Exception as exc:
            db.rollback()
            cursor = db.scalar(select(IntegrationCursor).where(IntegrationCursor.source == "EXIT_ORDERS"))
            if not cursor:
                cursor = IntegrationCursor(source="EXIT_ORDERS")
                db.add(cursor)
            cursor.last_error = str(exc)[:4000]
            db.commit()
            logger.exception("Falló la sincronización de pedidos EXIT")
            return 0
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": LOCK_ID})
            db.commit()


def main():
    interval = max(5, settings.exit_order_sync_interval_seconds)
    logger.info("Demonio de pedidos EXIT iniciado; intervalo=%ss", interval)
    while True:
        started = time.monotonic()
        sync_once()
        elapsed = time.monotonic() - started
        time.sleep(max(1, interval - elapsed))


if __name__ == "__main__":
    main()
