"""Reintenta el traslado verificado de operador a RPA; no restablece una clave existente."""
from app.db import SessionLocal
from app.operator_access import provision_rpa

if __name__ == '__main__':
    with SessionLocal() as db:
        created = provision_rpa(db)
        print('RPA habilitado; debe cambiar su contraseña inicial al entrar.' if created else 'RPA ya existe; contraseña y permisos conservados.')
