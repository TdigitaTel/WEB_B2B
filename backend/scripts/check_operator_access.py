import getpass
import sys

from sqlalchemy import func, select

from app.auth import verify_password
from app.db import SessionLocal
from app.models import User
from app.delegations import fetch_delegations, resolve_delegation


def main():
    login = sys.argv[1].strip().lower() if len(sys.argv) > 1 else None
    with SessionLocal() as db:
        if not login:
            delegations = fetch_delegations()
            rows = db.scalars(select(User).where(User.role.in_(["OPERADOR_TIENDA", "ADMIN"])).order_by(User.email)).all()
            print([{"usuario": user.email, "rol": user.role, "activo": user.active,
                    "delegacion": (getattr(resolve_delegation(user.delegation_code, delegations, company_code=user.company_code), "name", user.store_id) if user.store_id else "Todas")} for user in rows])
            return
        user = db.scalar(select(User).where(func.lower(User.email) == login))
        if not user:
            raise SystemExit(f"El usuario '{login}' no existe en PostgreSQL")
        if user.role not in {"OPERADOR_TIENDA", "ADMIN"}:
            raise SystemExit(f"El usuario existe, pero su rol es {user.role}")
        store = resolve_delegation(user.delegation_code, company_code=user.company_code) if user.store_id else None
        password = getpass.getpass("Contraseña que quieres comprobar: ")
        valid = bool(user.active and verify_password(password, user.password_hash))
        print({"usuario": user.email, "password_correcta": valid, "activo": user.active,
               "rol": user.role, "almacen": store.name if store else "Todos"})
        if not valid:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
