"""One explicitly confirmed historical delivery; never infer pickup from invoicing."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select
from .auth import audit
from .exit_order_key import stored_key
from .models import (Order, OrderItem, OrderStatusHistory, User, OrderDeliveryNote,
                     OrderDeliveryNoteLine, OrderPickup, OrderPickupLine)

WEB_NUMBER = 'WEB-2026-0000260'
ORDER_KEY = (1, 2026, 'AL', '6007768')
NOTE_KEY = (1, 2026, 'AL', '682017735')
EXPECTED = {'5': '21679', '10': '23538'}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def repair_confirmed_historical_pickup(db, apply=False):
    """Attach the original WEB pickup to its two lines, keeping time and actor.

    Dry run by default. Caller owns the transaction. Any mismatch leaves it alone.
    """
    order = db.scalar(select(Order).where(Order.order_number == WEB_NUMBER).with_for_update())
    if not order:
        return {'status': 'absent'}
    def skip(reason):
        return {'status': 'skipped', 'reason': reason}
    if order.origen_pedido != 'B2B' or order.customer_code != '11264' or stored_key(order) != ORDER_KEY or order.deleted_at:
        return skip('La identidad del pedido no coincide')
    request_id = str(uuid5(NAMESPACE_URL, f'webb2b:historical-delivery:{WEB_NUMBER}:682017735'))
    existing = db.scalar(select(OrderPickup).where(OrderPickup.order_id == order.id))
    if existing:
        return {'status': 'already_recorded'} if existing.request_id == request_id else skip('Ya hay recogidas registradas; requiere revisión')
    stamp = order.delivered_at
    if not stamp or utc(stamp).strftime('%Y-%m-%dT%H:%M') != '2026-10-26T15:38':
        return skip('No coincide la fecha de entrega histórica confirmada')
    history = list(db.scalars(select(OrderStatusHistory).where(
        OrderStatusHistory.order_id == order.id, OrderStatusHistory.estado_registro_exit == 'ENTREGADO',
        OrderStatusHistory.source == 'WEB')))
    actors = {row.changed_by_user_id for row in history if row.changed_by_user_id and utc(row.created_at) == utc(stamp)}
    if len(actors) != 1 or not db.get(User, next(iter(actors))):
        return skip('No se puede verificar el operador de la entrega original')
    items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    if len(items) != 2 or {item.sku for item in items} != set(EXPECTED.values()) or any(item.exit_removed_at or item.quantity != 1 or item.unit.strip().upper() != 'UD' for item in items):
        return skip('No coinciden los dos materiales originales')
    note = db.scalar(select(OrderDeliveryNote).where(
        OrderDeliveryNote.order_id == order.id, OrderDeliveryNote.company_code == NOTE_KEY[0],
        OrderDeliveryNote.year == NOTE_KEY[1], OrderDeliveryNote.series == NOTE_KEY[2], OrderDeliveryNote.number == NOTE_KEY[3]))
    if not note or not note.current or note.status not in {'EMITIDO','FACTURADO'}:
        return skip('El albarán confirmado no está disponible')
    lines = list(db.scalars(select(OrderDeliveryNoteLine).where(OrderDeliveryNoteLine.delivery_note_id == note.id)))
    by_id = {item.id: item for item in items}
    if len(lines) != 2 or {line.line_number for line in lines} != set(EXPECTED) or any(
        not line.current or line.warning or line.quantity != 1 or line.sku != EXPECTED.get(line.line_number)
        or line.unit.strip().upper() != 'UD' or line.order_item_id not in by_id
        or by_id[line.order_item_id].sku != line.sku for line in lines):
        return skip('El desglose de albarán requiere revisión')
    if db.scalar(select(OrderPickupLine.id).where(OrderPickupLine.delivery_line_id.in_([line.id for line in lines])).limit(1)):
        return skip('Una línea ya figura recogida; requiere revisión')
    report = {'status': 'applied' if apply else 'ready', 'web_number': WEB_NUMBER,
              'delivered_at': utc(stamp).isoformat(), 'line_ids': [line.id for line in lines]}
    if not apply:
        return report
    event = OrderPickup(order_id=order.id, request_id=request_id, confirmed_by=next(iter(actors)),
                        confirmed_at=stamp, observation='Regularización de entrega WEB anterior al desglose por albarán. Entrega total confirmada por el usuario el 03/11/2026; se conserva fecha y operador originales.')
    db.add(event); db.flush()
    for line in lines:
        db.add(OrderPickupLine(pickup_id=event.id, delivery_line_id=line.id, quantity=line.quantity))
    order.pickup_managed_at = order.pickup_managed_at or datetime.now(timezone.utc)
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit='ENTREGADO_TOTAL', source='HISTORICAL_REPAIR',
                             note='Desglose de la entrega histórica confirmado por el usuario. Se conservan fecha y operador originales.'))
    audit(db, None, 'HISTORICAL_PICKUP_REGULARIZED', 'ORDER', order.public_id, report)
    db.info.pop('pickup_summary_cache', None)
    db.flush()
    return report


if __name__ == '__main__':
    import argparse
    import json
    from .db import SessionLocal
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Aplicar la regularización confirmada')
    args = parser.parse_args()
    with SessionLocal() as db:
        result = repair_confirmed_historical_pickup(db, apply=args.apply)
        if args.apply:
            db.commit()
        print(json.dumps(result, ensure_ascii=False))
