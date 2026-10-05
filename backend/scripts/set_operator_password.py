import getpass
import sys

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import User
from app.delegations import fetch_delegations, resolve_delegation


def main():
    if len(sys.argv) not in {3, 4}:
        raise SystemExit("Uso: python -m scripts.set_operator_password email@empresa.es CODIGO_DELEGACION ['Nombre del operador']")
    email = sys.argv[1].strip().lower()
    store_code = sys.argv[2].strip().upper()
    full_name = sys.argv[3].strip() if len(sys.argv) == 4 else email
    password = getpass.getpass("Nueva contraseña de operación: ")
    confirmation = getpass.getpass("Repite la contraseña: ")
    if len(password) < 8:
        raise SystemExit("La contraseña debe tener al menos 8 caracteres")
    if password != confirmation:
        raise SystemExit("Las contraseñas no coinciden")

    with SessionLocal() as db:
        store = resolve_delegation(store_code)
        if not store:
            available = ", ".join(d.id for d in fetch_delegations())
            raise SystemExit(f"La delegación {store_code} no existe. Disponibles: {available}")
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if not user:
            user = User(email=email, full_name=full_name, password_hash="", role="OPERADOR_TIENDA", active=True)
            db.add(user)
        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.role = "OPERADOR_TIENDA"
        user.store_id = store.id
        user.customer_id = None
        user.erp_customer_code = None
        user.active = True
        store_name = store.name
        db.commit()
    print({"status": "ok", "email": email, "role": "OPERADOR_TIENDA", "store": store_name})


if __name__ == "__main__":
    main()
