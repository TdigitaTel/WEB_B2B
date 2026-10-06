"""Fechas de gestión EXIT separadas de los estados visibles al cliente."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .config import settings
from .models import Order, OrderStatusHistory

MADRID = ZoneInfo('Europe/Madrid')

def instant(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=MADRID) if value.tzinfo is None else value.astimezone(MADRID)
    return datetime.combine(value, time.min, MADRID)

def with_hour(day, clock):
    day, clock = instant(day), instant(clock)
    if day is None:
        return None
    return datetime.combine(day.date(), clock.timetz(), MADRID) if clock else day

def preparation_time(prepared, registered):
    prepared, registered = instant(prepared), instant(registered)
    if prepared is None or prepared.time() != time.min or registered is None:
        return prepared
    # Se conserva el día de preparación; el incremento puede cruzar medianoche.
    return with_hour(prepared, registered) + timedelta(seconds=settings.exit_preparation_offset_seconds)

def exit_events(record, delivery=None):
    delivery = delivery or {}
    events = [('REGISTRADO', instant(record.recorded_at), 'Registro del pedido en EXIT')]
    events.append(('EN_PREPARACION', preparation_time(record.prepared_at, record.recorded_at), 'Preparación del pedido en EXIT'))
    if delivery:
        events.append(('ATENDIDO', instant(delivery.get('attended_at')), f"Albarán {delivery.get('delivery_number', '')} generado"))
        if delivery.get('is_printed'):
            events.append(('ENTREGADO', with_hour(record.delivered_at or delivery.get('delivered_at'), record.source_updated_at), 'Albarán impreso en EXIT'))
        if delivery.get('is_invoiced'):
            invoice = instant(record.invoiced_at or delivery.get('invoiced_at'))
            events.append(('FACTURADO', invoice.replace(hour=0, minute=0, second=0, microsecond=0) if invoice else None, 'Factura generada en EXIT'))
    return [(state, stamp, note) for state, stamp, note in events if stamp is not None]

def sync_history(db, order, events):
    db.execute(select(Order.id).where(Order.id == order.id).with_for_update()).all()
    history = db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)).all()
    for state, stamp, note in events:
        existing = next((h for h in history if h.source == 'EXIT' and h.estado_registro_exit in ({'EN_PROCESO', 'EN_PREPARACION'} if state == 'EN_PREPARACION' else {state})), None)
        if existing:
            existing.estado_registro_exit, existing.created_at, existing.note = state, stamp, note
        else:
            existing = OrderStatusHistory(order_id=order.id, estado_registro_exit=state, source='EXIT', created_at=stamp, note=note)
            db.add(existing)
            history.append(existing)
    db.flush()
