"""Permiso de delivery por cliente EXIT, compartido por cuenta y subusuarios."""
from fastapi import HTTPException
from .models import CustomerDeliverySetting


def delivery_enabled(db, customer_code):
    setting = db.get(CustomerDeliverySetting, customer_code) if customer_code else None
    return bool(setting and setting.delivery_enabled)


def validate_delivery(db, customer_code, method, address):
    if method != "DELIVERY":
        return None
    if not delivery_enabled(db, customer_code):
        raise HTTPException(403, "Este cliente solo tiene habilitada la recogida en tienda")
    address = (address or "").strip()
    if not address:
        raise HTTPException(422, "Indica la dirección de delivery")
    return address
