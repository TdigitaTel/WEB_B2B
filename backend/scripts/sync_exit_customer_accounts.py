"""Crea en PostgreSQL accesos inactivos para códigos nuevos detectados en EXIT."""
import argparse
import secrets
import time

from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.db import SessionLocal
from app.erp_db import fetch_customer_codes
from app.models import User


def sync_once(after_code: str = "", batch_size: int = 30) -> dict:
    codes = fetch_customer_codes(after_code=after_code, limit=batch_size)
    created = 0
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        existing_codes = {str(user.erp_customer_code).strip() for user in users if user.erp_customer_code}
        existing_usernames = {user.email.strip().lower() for user in users}
        for code in codes:
            if code in existing_codes or code.lower() in existing_usernames:
                continue
            db.add(User(
                email=code.lower(), full_name=code, erp_customer_code=code,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                role="CLIENTE_ADMIN", customer_id=None, active=False,
            ))
            created += 1
        db.commit()
    next_code = codes[-1] if codes else ""
    result = {"status": "ok", "checked": len(codes), "created": created,
              "from_after": after_code or None, "next_after": next_code or None}
    print(result, flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=settings.customer_sync_interval_seconds,
                        help="Segundos entre revisiones")
    parser.add_argument("--batch-size", type=int, default=settings.customer_sync_batch_size,
                        help="Cantidad máxima de clientes consultados en cada ciclo")
    args = parser.parse_args()
    after_code = ""
    while True:
        try:
            result = sync_once(after_code=after_code, batch_size=args.batch_size)
            after_code = result["next_after"] or ""
        except Exception as exc:
            print({"status": "error", "error": str(exc)}, flush=True)
        if not args.watch:
            break
        time.sleep(max(2, args.interval))


if __name__ == "__main__":
    main()
