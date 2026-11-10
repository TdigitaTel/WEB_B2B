"""Persist state changes in the same transaction as the order; no SMTP in requests."""
import json
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from . import order_pickups
from .models import (CustomerOrderEmailSetting, Order, OrderItem, OrderStatusHistory,
                     OrderDeliveryNote, OrderDeliveryNoteLine, OrderPickup, OrderPickupLine,
                     OrderEmailCheckpoint, OrderEmailDelivery, OrderEmailSettings)
from .order_email_texts import LABELS, STATES, customer_mail_state


def snapshot(db, order):
    summary = order_pickups.summary(db, order)
    raw = order.estado_registro_exit
    state = customer_mail_state(raw,summary)
    if raw == 'ELIMINADO_EN_EXIT' or order.reconciliation_reason == 'MISSING_EXIT':
        state = raw = 'ELIMINADO_EN_EXIT'
    state = state if state in LABELS else 'EN_GESTION'
    payload = {'web_number': order.order_number, 'exit_number': order.exit_order_number or order.nro_pedido_exit,
               'state': raw, 'pickup_summary': summary, 'expected_at': order.attention_deadline_at,
               'delivered_at': order.delivered_at,
               'items': [{'sku': item.sku, 'description': item.description, 'quantity': item.quantity,
                          'unit': item.unit, 'removed_in_exit': bool(item.exit_removed_at)}
                         for item in db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id))]}
    # Include invoicing as a separate change without concealing the actual pickup state.
    key = state + (':FACTURADO' if raw == 'FACTURADO' else '')
    return key, ('FACTURADO' if raw == 'FACTURADO' else state), json.loads(json.dumps(payload, default=lambda value: value.isoformat() if isinstance(value, (date, datetime)) else float(value) if isinstance(value, Decimal) else str(value)))


def observe(db, order, baseline=False):
    if order.origen_pedido != 'B2B' or not order.customer_code:
        return
    choice = db.get(CustomerOrderEmailSetting, order.customer_code)
    if not choice or not (choice.email1_enabled or choice.email2_enabled):
        return
    db.scalar(select(Order.id).where(Order.id == order.id).with_for_update())
    db.info.pop('pickup_summary_cache', None)
    key, state, payload = snapshot(db, order)
    checkpoint = db.get(OrderEmailCheckpoint, order.id, populate_existing=True)
    if checkpoint and checkpoint.state == key:
        # Later flushes may add the lines after creating the order. Keep the queued
        # snapshot complete, without creating another notification for the same state.
        job = next((value for value in db.new if isinstance(value, OrderEmailDelivery)
                    and value.order_id == order.id and value.revision == checkpoint.revision), None)
        if job is None:
            job = db.scalar(select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order.id,
                            OrderEmailDelivery.revision == checkpoint.revision, OrderEmailDelivery.status == 'PENDING'))
        if job is not None:
            job.payload = payload
        return
    if checkpoint is None:
        checkpoint = OrderEmailCheckpoint(order_id=order.id, state='', revision=0)
        db.add(checkpoint)
    checkpoint.state = key
    checkpoint.revision += 1
    setting = db.get(OrderEmailSettings, 1)
    config = setting.configuration if setting else {}
    if (baseline or not config.get('automatic_enabled') or order.deleted_at
            or order.estado_registro_exit == 'BORRADOR' or state not in STATES or state not in config.get('selected_states', [])):
        return
    db.add(OrderEmailDelivery(order_id=order.id, revision=checkpoint.revision, state=state, payload=payload))


def baseline_customer(db, code):
    db.flush()
    for order in db.scalars(select(Order).where(Order.customer_code == code, Order.origen_pedido == 'B2B')):
        for job in db.scalars(select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order.id,
                              OrderEmailDelivery.status.in_(['PENDING', 'RETRY']))):
            job.status = 'CANCELLED'
        observe(db, order, baseline=True)


def baseline_all(db):
    for choice in db.scalars(select(CustomerOrderEmailSetting)):
        baseline_customer(db, choice.customer_code)


@event.listens_for(Session, 'before_flush')
def remember_orders(db, flush_context, instances):
    pending = db.info.setdefault('mail_changed_orders', set())
    ids = db.info.setdefault('mail_changed_ids', set())
    for value in db.new.union(db.dirty):
        if isinstance(value, Order):
            pending.add(value)
        elif isinstance(value, (OrderItem, OrderStatusHistory, OrderDeliveryNote, OrderPickup)) and value.order_id:
            ids.add(value.order_id)
        elif isinstance(value, OrderPickupLine) and value.pickup_id:
            pickup = db.get(OrderPickup, value.pickup_id)
            if pickup:
                ids.add(pickup.order_id)
        elif isinstance(value, OrderDeliveryNoteLine) and value.delivery_note_id:
            note = db.get(OrderDeliveryNote, value.delivery_note_id)
            if note:
                ids.add(note.order_id)


@event.listens_for(Session, 'after_flush_postexec')
def persist_changes(db, flush_context):
    pending = db.info.pop('mail_changed_orders', set())
    ids = db.info.pop('mail_changed_ids', set())
    pending.update(order for oid in ids if (order := db.get(Order, oid)) is not None)
    for order in sorted(pending, key=lambda value: value.id):
        observe(db, order)


@event.listens_for(Session, 'after_soft_rollback')
def clear_pending(db, previous_transaction):
    db.info.pop('mail_changed_orders', None)
    db.info.pop('mail_changed_ids', None)
