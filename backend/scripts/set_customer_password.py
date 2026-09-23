import getpass
import sys

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.erp_db import fetch_customer
from app.models import User


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python -m scripts.set_customer_password CODIGO_CLIENTE email@empresa.es")
    customer_code, email = sys.argv[1].strip(), sys.argv[2].strip().lower()
    customer = fetch_customer(customer_code)
    if not customer:
        raise SystemExit(f"El cliente {customer_code} no existe en EXITERP")
    password = getpass.getpass("Nueva contraseña: ")
    confirmation = getpass.getpass("Repite la contraseña: ")
    if not password or password != confirmation:
        raise SystemExit("Las contraseñas no coinciden")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if not user:
            user = User(email=email, full_name=email, role="CLIENTE_ADMIN", active=True)
            db.add(user)
        user.password_hash = hash_password(password)
        user.erp_customer_code = customer_code
        user.customer_id = None
        db.commit()
    print({"status": "ok", "email": email, "customer_code": customer_code})


if __name__ == "__main__":
    main()
