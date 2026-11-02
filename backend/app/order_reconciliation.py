"""Retire confirmed missing EXIT orders and their duplicate local projections."""
from datetime import datetime, timezone
import logging
from sqlalchemy import select
from .models import Order
from .auth import audit
from .exit_order_key import stored_key, record_key
from .exit_db import fetch_existing_exit_order_keys
logger = logging.getLogger(__name__)
CLOSED = {'ATENDIDO', 'ENTREGADO', 'FACTURADO'}

def normalize(key):
    if not key or any(value is None for value in key):
        return None
    try:
        company, year, series, number = key
        number = str(number).strip()
        if not number:
            return None
        return int(company), int(year), str(series).strip().upper(), number
    except (ValueError, TypeError):
        return None


def reconcile_orders(db, rows, all_rows, records, delivery_keys, user, notes_available=True):
    """Only confirmed exact identities may be retired; never infer deletion from a range."""
    # Freeze only the displayed identities and their peers while checking EXIT.
    # A simultaneous RPA relink must not retire the new identity using an old read.
    touched = {normalize(stored_key(row)) for row in rows} - {None}
    ids = [row.id for row in all_rows if normalize(stored_key(row)) in touched]
    if ids:
        db.flush()
        db.scalars(select(Order).where(Order.id.in_(ids)).order_by(Order.id).with_for_update()
                   .execution_options(populate_existing=True)).all()
    visible = {normalize(record_key(record)) for record in records}
    visible.discard(None)
    delivered = {normalize(key) for key in delivery_keys}
    keyed = {row.id: normalize(stored_key(row)) for row in rows}
    to_check = {key for row in rows if (key := keyed[row.id]) and key not in visible
                and not row.delivered_at and row.estado_registro_exit not in CLOSED and key not in delivered}
    checked = True
    try:
        existing = visible | fetch_existing_exit_order_keys(sorted(to_check))
    except Exception:
        # A failed/incomplete query is never evidence of a deletion.
        logger.exception('No se pudo verificar la existencia exacta de los pedidos EXIT; no se retiran pedidos')
        existing = visible
        checked = False
    groups = {}
    for row in all_rows:
        key = normalize(stored_key(row))
        if key:
            groups.setdefault(key, []).append(row)
    for key in touched:
        peers = groups.get(key, [])
        web = [row for row in peers if row.origen_pedido == 'B2B']
        canonical = web[0] if len(web) == 1 else None
        for row in peers:
            previous = row.reconciliation_reason
            reason = None
            if row.origen_pedido == 'EXIT' and canonical:
                reason = 'DUPLICATE_EXIT'
            elif (checked and notes_available and key in to_check and key not in existing
                  and not row.delivered_at and row.estado_registro_exit not in CLOSED and key not in delivered):
                reason = 'MISSING_EXIT'
            elif key not in existing:
                continue  # No authoritative proof to change this row.
            if reason == previous:
                continue
            row.reconciliation_reason = reason
            row.reconciliation_hidden_at = datetime.now(timezone.utc) if reason else None
            audit(db, user, 'ORDER_RECONCILED', 'ORDER', row.public_id,
                  {'previous': previous, 'reason': reason, 'exit_key': list(key),
                   'canonical_order': canonical.public_id if canonical else None})
    return {row.public_id for row in all_rows if row.reconciliation_hidden_at is not None}
