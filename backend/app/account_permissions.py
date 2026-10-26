"""Identidad comercial común y permisos vigentes de cada usuario."""
from fastapi import HTTPException
from .models import User, Customer

CUSTOMER_ROLES = {"CLIENTE", "CLIENTE_ADMIN"}


def official_code(user, db):
    if user.erp_customer_code:
        return user.erp_customer_code.strip()
    customer = db.get(Customer, user.customer_id) if user.customer_id else None
    return customer.erp_id.strip() if customer else ""


def principal_for(user, db):
    if not user.parent_user_id:
        return user
    principal = db.get(User, user.parent_user_id)
    if (not principal or not principal.active or principal.parent_user_id is not None
            or principal.role not in CUSTOMER_ROLES or user.role not in CUSTOMER_ROLES
            or official_code(principal, db) != official_code(user, db) or principal.customer_id != user.customer_id):
        raise HTTPException(401, "La cuenta principal está deshabilitada o la vinculación no es válida")
    return principal


def effective_permissions(user, db):
    principal = principal_for(user, db)
    return {name: bool(getattr(user, name)) and bool(getattr(principal, name))
            for name in ("can_view_prices", "can_view_delivery_notes", "can_view_invoices", "can_manage_preferences")}


def identity(user, db):
    principal = principal_for(user, db)
    from .operator_permissions import permissions_for
    return {"operator_permissions": permissions_for(user, db), **effective_permissions(user, db), "is_subuser": user.parent_user_id is not None,
            "can_manage_subusers": user.role in CUSTOMER_ROLES and user.parent_user_id is None,
            "own_orders_only": bool(user.own_orders_only), "principal_user_name": principal.full_name,
            "login_name": user.full_name, "access_code": user.access_code or official_code(user, db),
            "contact_phone": user.contact_phone or ""}
