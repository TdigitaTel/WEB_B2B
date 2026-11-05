"""Revocable, read-only order tracking. Bearer secrets are stored only as hashes."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import order_pickups
from .auth import audit, require_roles
from .db import get_db
from .models import Order, OrderItem, OrderLinePlanning, OrderTrackingLink, User, OrderStatusHistory
from .operator_permissions import can_operate_delegation
from .exit_order_key import record_key, stored_key
from .exit_db import fetch_customer_exit_orders
from .erp_db import fetch_delivery_statuses_for_orders, fetch_customer_delivery_notes

router = APIRouter(tags=["Seguimiento de pedidos"])
operator = require_roles("OPERADOR_TIENDA", "ADMIN")
LIFETIME_DAYS = 30


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def no_store(response):
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


def scoped_order(db, user, order_id):
    order = db.scalar(select(Order).where(Order.public_id == order_id, Order.origen_pedido == "B2B").with_for_update())
    if not order or not can_operate_delegation(user, db, order.company_code, order.delegation_code):
        raise HTTPException(404, "Pedido WEB no encontrado")
    return order


def active_links(db, order):
    return list(db.scalars(select(OrderTrackingLink).where(OrderTrackingLink.order_id == order.id,
                                                          OrderTrackingLink.revoked_at.is_(None))))


@router.get("/api/v1/store/orders/{order_id}/tracking-link")
def link_status(order_id: str, response: Response, db: Session = Depends(get_db), user: User = Depends(operator)):
    no_store(response)
    order = scoped_order(db, user, order_id)
    now = datetime.now(timezone.utc)
    active = next((link for link in active_links(db, order) if utc(link.expires_at) > now), None)
    return {"active": active is not None, "expires_at": active.expires_at if active else None, "lifetime_days": LIFETIME_DAYS}


@router.post("/api/v1/store/orders/{order_id}/tracking-link")
def create_link(order_id: str, response: Response, db: Session = Depends(get_db), user: User = Depends(operator)):
    no_store(response)
    order = scoped_order(db, user, order_id)
    if order.estado_registro_exit == "BORRADOR":
        raise HTTPException(409, "Envía el pedido antes de compartir su seguimiento")
    now = datetime.now(timezone.utc)
    for link in active_links(db, order):
        link.revoked_at = now
    token = secrets.token_urlsafe(32)
    expires = now + timedelta(days=LIFETIME_DAYS)
    db.add(OrderTrackingLink(order_id=order.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                             created_by_user_id=user.id, expires_at=expires))
    audit(db, user, "ORDER_TRACKING_LINK_CREATED", "ORDER", order.public_id, {"expires_at": expires.isoformat()})
    db.commit()
    # A fragment is not sent in page requests, referrers or server access logs.
    return {"path": f"/seguimiento#token={token}", "expires_at": expires, "lifetime_days": LIFETIME_DAYS}


@router.delete("/api/v1/store/orders/{order_id}/tracking-link")
def revoke_link(order_id: str, response: Response, db: Session = Depends(get_db), user: User = Depends(operator)):
    no_store(response)
    order = scoped_order(db, user, order_id)
    for link in active_links(db, order):
        link.revoked_at = datetime.now(timezone.utc)
    audit(db, user, "ORDER_TRACKING_LINK_REVOKED", "ORDER", order.public_id)
    db.commit()
    return {"active": False}


class TrackingRead(BaseModel):
    token: str = Field(min_length=40, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/api/v1/order-tracking/read")
def read_tracking(body: TrackingRead, response: Response, db: Session = Depends(get_db)):
    no_store(response)
    link = db.scalar(select(OrderTrackingLink).where(OrderTrackingLink.token_hash == hashlib.sha256(body.token.encode()).hexdigest()))
    now = datetime.now(timezone.utc)
    if not link or link.revoked_at or utc(link.expires_at) <= now:
        raise HTTPException(404, "El enlace de seguimiento no está disponible o ha caducado")
    order = db.get(Order, link.order_id)
    if not order or order.deleted_at:
        raise HTTPException(404, "El enlace de seguimiento no está disponible o ha caducado")
    state = order.estado_registro_exit
    remote = None
    warning = None
    identity = stored_key(order)
    if identity and order.customer_code:
        try:
            records = fetch_customer_exit_orders(order.customer_code, order.created_at.date(), now.date(), order_number=str(identity[3]))
            matches = [record for record in records if record_key(record) == identity and record.customer_code == order.customer_code]
            if len(matches) == 1:
                remote = matches[0]
                state = remote.estado_registro_exit
            else:
                warning = "Se muestra el seguimiento guardado; no se pudo confirmar el pedido en EXIT."
        except Exception:
            warning = "Se muestra el seguimiento guardado; la actualización está temporalmente no disponible."
        try:
            notes = fetch_delivery_statuses_for_orders([identity])
            from .delivery_links import note_order_key
            notes = [note for note in notes if note_order_key(note) == identity]
            if any(note.get("is_invoiced") for note in notes):
                state = "FACTURADO"
            elif notes:
                state = "ATENDIDO"
        except Exception:
            warning = warning or "No se pudo confirmar el último estado de entrega; se mantienen los datos disponibles."
    if order.delivered_at and state != "FACTURADO":
        state = "ENTREGADO"
    elif state == "ENTREGADO" and not order.delivered_at:
        state = "ATENDIDO"  # EXIT served is not the customer's physical pickup.
    if order.reconciliation_reason == "MISSING_EXIT" and remote is None:
        state = "ELIMINADO_EN_EXIT"
    planning = db.get(OrderLinePlanning, f"WEB:{order.public_id}")
    saved = planning.lines if planning else {}
    items = []
    stored_items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)))
    for item in stored_items:
        served = item.served_quantity if item.served_quantity is not None else max(0, item.quantity - (item.pending_quantity if item.pending_quantity is not None else item.quantity))
        removed = bool(getattr(item, "exit_removed_at", None))
        if remote:
            candidates = [line for line in remote.lines if line.sku == item.sku and
                          (line.line_number == item.exit_line_number if item.exit_line_number else
                           sum(1 for other in remote.lines if other.sku == item.sku) == 1 and
                           sum(1 for other in stored_items if other.sku == item.sku) == 1)]
            if item.exit_line_number:
                removed = not candidates
            if len(candidates) == 1:
                line = candidates[0]
                served = line.served_quantity if line.served_quantity is not None else max(0, line.quantity - (line.pending_quantity if line.pending_quantity is not None else line.quantity))
        plan = saved.get(str(item.id), {})
        if plan.get("sku") != item.sku:
            plan = {}
        items.append({"line_key": str(item.id), "sku": item.sku, "description": item.description,
                      "quantity": float(item.quantity), "unit": item.unit, "served_quantity": float(served),
                      "expected_at": plan.get("expected_at"), "situation": plan.get("status"),
                      "removed_in_exit": removed, "created_in_web": item.created_in_web})
    pickup_summary = order_pickups.summary(db, order)
    if identity and order.customer_code:
        try:
            documents = fetch_customer_delivery_notes(order.customer_code, 1000, order_keys=[identity])
            if len(documents) >= 1000:
                raise ValueError("Consulta incompleta")
            pickup_summary = order_pickups.preview_summary(db, order, documents, remote)
        except Exception:
            warning = warning or "No se pudo actualizar el detalle de albaranes; se muestra el último seguimiento guardado."
    # Public timeline contains states and dates only, never actor names or notes.
    timeline = []
    allowed = {'BORRADOR','PENDIENTE','BLOQUEADO','REGISTRADO','EN_PROCESO','EN_PREPARACION',
               'ATENDIDO','PENDIENTE_RECOJO','PENDIENTE_RECOGIDA_PARCIAL','PENDIENTE_RECOGIDA_TOTAL',
               'ENTREGADO','ENTREGADO_PARCIAL','ENTREGADO_TOTAL','FACTURADO'}
    for event in db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id).order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)):
        if event.estado_registro_exit not in allowed:
            continue
        if order.origen_pedido == 'B2B' and event.source == 'EXIT' and event.estado_registro_exit.startswith('ENTREGADO'):
            continue  # Printing a delivery note is not physical collection.
        timeline.append({'etapa':event.estado_registro_exit,'completed_at':event.created_at,
                         'date_only':event.estado_registro_exit == 'FACTURADO'})
    # Explicit allowlist: no prices, customer/contact data, notes, documents or mutation URLs.
    return {"web_number": order.order_number, "exit_number": str(identity[3]) if identity else order.nro_pedido_exit,
            "pickup_date": order.pickup_date, "pickup_slot_start": order.pickup_slot_start, "pickup_slot_end": order.pickup_slot_end, "state": state, "expected_at": order.attention_deadline_at, "delivered_at": order.delivered_at,
            "pickup_summary": pickup_summary, "workflow":timeline, "registered_at":order.fecha_registro_exit, "items": items, "checked_at": now, "warning": warning, "expires_at": link.expires_at}
