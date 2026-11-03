"""Immutable collection ledger. EXIT notes prove preparation; WEB events prove pickup."""
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from .models import Order, OrderItem, OrderDeliveryNote as Note, OrderDeliveryNoteLine as Line, OrderPickup as Pickup, OrderPickupLine as Picked, OrderStatusHistory
from .delivery_links import matches_note, order_key


def number(value):
    try:
        result = Decimal(str(value or 0))
        return result if result.is_finite() else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def sync_documents(db, order, documents):
    """Called only with a successful complete customer note snapshot. Never hard-delete."""
    db.scalar(select(Order.id).where(Order.id == order.id).with_for_update())
    db.info.pop("pickup_summary_cache", None)
    now = datetime.now(timezone.utc)
    existing = list(db.scalars(select(Note).where(Note.order_id == order.id)))
    for note in existing:
        note.current = False
    items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    received = {row.delivery_line_id: row for row in db.scalars(select(Picked).join(Line, Picked.delivery_line_id == Line.id).join(Note).where(Note.order_id == order.id))}
    seen_documents = set()
    for doc in documents:
        if not matches_note(doc, order):
            continue
        parts = str(doc.get('number') or '').replace('~', '/').replace('-', '/').split('/')
        if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit():
            raise HTTPException(409, 'No se puede identificar la llave completa de un albarán')
        key = (int(doc['company_code']), int(parts[0]), parts[1].strip().upper(), parts[2])
        if key in seen_documents:
            raise HTTPException(409, 'EXIT devuelve un albarán repetido; revisa la consulta')
        seen_documents.add(key)
        note = db.scalar(select(Note).where(Note.company_code == key[0], Note.year == key[1], Note.series == key[2], Note.number == key[3]))
        if note and note.order_id != order.id:
            raise HTTPException(409, 'El albarán ya está asociado a otro pedido; requiere revisión')
        if not note:
            note = Note(order_id=order.id, company_code=key[0], year=key[1], series=key[2], number=key[3], status='', synced_at=now)
            db.add(note); db.flush()
        note.current = True; note.status = doc.get('status') or ''; note.synced_at = now
        old = {line.line_number: line for line in db.scalars(select(Line).where(Line.delivery_note_id == note.id))}
        for line in old.values():
            line.current = False
        seen_lines = set()
        for source in doc.get('items', []):
            line_number = str(source.get('line') or '')
            if not line_number or line_number in seen_lines:
                raise HTTPException(409, 'EXIT devuelve líneas sin identificador único; no se registra la recogida')
            seen_lines.add(line_number)
            sku = str(source.get('sku') or '').strip()
            unit = str(source.get('unit') or 'UD').strip().upper()
            quantity = number(source.get('quantity'))
            candidates = [item for item in items if item.sku == sku and item.unit.strip().upper() == unit]
            source_line = source.get('order_line_number')
            if source_line is not None:
                candidates = [item for item in candidates if item.exit_line_number == str(source_line)]
            target = candidates[0] if len(candidates) == 1 else None
            warning = None if target else 'No se puede identificar de forma única la línea del pedido'
            if target and target.exit_removed_at:
                warning = 'Material eliminado en EXIT: no se puede recoger'
            if quantity <= 0:
                warning = 'Cantidad no positiva: requiere revisión (devolución o anulación)'
            row = old.get(line_number)
            if row and row.id in received:
                if (row.sku, row.unit, row.quantity, row.order_item_id) != (sku, unit, quantity, target.id if target else None):
                    warning = 'Albarán modificado después de la recogida: se conserva el registro original'
                # Never remap or rewrite the evidence of a physical collection.
                row.current = True; row.warning = warning
                continue
            if not row:
                row = Line(delivery_note_id=note.id, line_number=line_number, sku=sku, description='', unit=unit, quantity=quantity)
                db.add(row)
            row.order_item_id = target.id if target else None
            row.sku = sku; row.unit = unit; row.quantity = quantity
            row.description = str(source.get('description') or sku)
            row.current = True; row.warning = warning
    order.pickup_managed_at = now
    db.flush()


def refresh_documents(db, orders, fetcher, strict=False):
    """One EXIT read per customer in a request; no date window or order status filter."""
    if not orders:
        return {}
    cache = db.info.setdefault('pickup_documents', {})
    warnings = {}
    customer_keys = defaultdict(list)
    for order in orders:
        key = order_key(order)
        if order.origen_pedido == "B2B" and key and order.customer_code:
            customer_keys[order.customer_code].append(key)
    for order in orders:
        if order.origen_pedido != 'B2B' or not order.nro_pedido_exit or not order.customer_code:
            continue
        if not order_key(order):
            if strict:
                raise HTTPException(409, 'Completa empresa, ejercicio, serie y número del pedido EXIT')
            warnings[order.id] = 'Falta la llave completa del pedido EXIT; revisa el vínculo'
            continue
        try:
            if order.customer_code not in cache:
                keys = list(dict.fromkeys(customer_keys[order.customer_code]))
                if not keys:
                    raise ValueError('Falta la llave completa del pedido EXIT')
                docs = []
                for offset in range(0, len(keys), 200):
                    batch = fetcher(order.customer_code, 1000, order_keys=keys[offset:offset+200])
                    if len(batch) >= 1000:
                        raise ValueError('Consulta de albaranes incompleta; requiere revisión')
                    docs.extend(batch)
                cache[order.customer_code] = docs
            with db.begin_nested():
                sync_documents(db, order, cache[order.customer_code])
                progress = summary(db, order)
                if progress and progress['last_pickup_at']:
                    order.delivered_at = progress['completed_at']
        except Exception as exc:
            if strict:
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(503, 'No se pudo verificar el detalle completo de albaranes en EXIT; no se ha registrado la recogida') from exc
            warnings[order.id] = 'No se pudo actualizar el detalle de albaranes; se conserva la última información'
    return warnings


def snapshot(db, order):
    items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)))
    notes = list(db.scalars(select(Note).where(Note.order_id == order.id).order_by(Note.year, Note.number)))
    rows = list(db.scalars(select(Line).join(Note).where(Note.order_id == order.id).order_by(Line.id)))
    collections = list(db.scalars(select(Pickup).where(Pickup.order_id == order.id).order_by(Pickup.confirmed_at, Pickup.id)))
    picked = list(db.scalars(select(Picked).join(Pickup).where(Pickup.order_id == order.id)))
    return items, notes, rows, collections, picked


def summary(db, order, data=None):
    if not order.pickup_managed_at:
        return None
    if data is None and order.id in db.info.get("pickup_summary_cache", {}):
        return db.info["pickup_summary_cache"][order.id]
    items, notes, rows, events, picked = data or snapshot(db, order)
    active = [item for item in items if not item.exit_removed_at and item.quantity > 0]
    note_by_id = {note.id: note for note in notes}
    picked_by_line = {row.delivery_line_id: row for row in picked}
    delivered = defaultdict(Decimal); available = defaultdict(Decimal)
    for line in rows:
        if line.order_item_id is None:
            continue
        if line.id in picked_by_line:
            delivered[line.order_item_id] += picked_by_line[line.id].quantity
        elif line.current and note_by_id[line.delivery_note_id].current and note_by_id[line.delivery_note_id].status in {'EMITIDO', 'FACTURADO'} and not line.warning:
            available[line.order_item_id] += line.quantity
    total = len(active)
    complete = sum(delivered[item.id] >= item.quantity for item in active)
    prepared = sum(delivered[item.id] + available[item.id] >= item.quantity for item in active)
    ready = sum(available[item.id] > 0 for item in active)
    any_delivered = any(delivered[item.id] > 0 for item in active)
    state = ('SIN_MATERIALES_ACTIVOS' if not total else 'ENTREGADO_TOTAL' if complete == total else
             ('PENDIENTE_RECOGIDA_TOTAL' if prepared == total else 'PENDIENTE_RECOGIDA_PARCIAL') if ready else
             'ENTREGADO_PARCIAL' if any_delivered else 'EN_PREPARACION')
    legacy = bool(order.delivered_at and not events)
    if legacy:
        state = 'REVISAR_ENTREGA_HISTORICA'
    return {'state': state, 'total_materials': total, 'prepared_materials': prepared,
            'delivered_materials': complete, 'partial_delivered_materials': sum(0 < delivered[item.id] < item.quantity for item in active),
            'ready_materials': ready, 'pending_materials': total-complete,
            'delivered_percent': complete*100//total if total else None,
            'prepared_percent': prepared*100//total if total else None,
            'prepared_complete': bool(total and prepared == total),
            'legacy_delivery': legacy, 'requires_review': legacy or any(line.warning for line in rows if line.current) or any(delivered[item.id] + available[item.id] > item.quantity for item in active),
            'last_pickup_at': events[-1].confirmed_at if events else None,
            'completed_at': events[-1].confirmed_at if events and state == 'ENTREGADO_TOTAL' else None,
            'lines': [{'line_key': str(item.id), 'delivered_quantity': float(delivered[item.id]),
                       'ready_quantity': float(available[item.id]), 'removed_in_exit': bool(item.exit_removed_at)} for item in items]}


def detail(db, order, warning=None):
    data = snapshot(db, order)
    items, notes, rows, events, picked = data
    by_line = {row.delivery_line_id: row for row in picked}
    by_event = {row.id: row for row in events}
    by_item = {row.id: row for row in items}
    documents = []
    for note in notes:
        lines = []
        for line in rows:
            if line.delivery_note_id != note.id:
                continue
            collected = by_line.get(line.id)
            item = by_item.get(line.order_item_id)
            eligible = note.current and line.current and note.status in {'EMITIDO','FACTURADO'} and not line.warning and item and not item.exit_removed_at and not collected
            lines.append({'id': line.id, 'line_number': line.line_number, 'sku': line.sku, 'description': line.description,
                          'quantity': float(line.quantity), 'unit': line.unit, 'can_collect': bool(eligible),
                          'collected_at': by_event[collected.pickup_id].confirmed_at if collected else None,
                          'warning': line.warning or (None if note.current and line.current else 'Ya no disponible en EXIT; se conserva el historial')})
        documents.append({'id': note.id, 'number': f'{note.year}/{note.series}/{note.number}', 'status': note.status, 'lines': lines})
    version = hashlib.sha256(json.dumps({'documents': documents,
        'items': [(item.id, str(item.quantity), bool(item.exit_removed_at)) for item in items]},
        sort_keys=True, default=lambda value: (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else str(value)).encode()).hexdigest()
    return {'version': version, 'summary': summary(db, order, data), 'documents': documents, 'warning': warning,
            'history': [{'id': event.id, 'confirmed_at': event.confirmed_at, 'confirmed_by': event.confirmed_by,
                         'observation': event.observation, 'line_ids': [row.delivery_line_id for row in picked if row.pickup_id == event.id]} for event in events]}


def confirm(db, order, actor, request_id, line_ids, observation):
    try:
        request_id = str(UUID(str(request_id)))
    except ValueError:
        raise HTTPException(422, 'Identificador de recogida no válido')
    previous = db.scalar(select(Pickup).where(Pickup.request_id == request_id))
    if previous:
        old = set(db.scalars(select(Picked.delivery_line_id).where(Picked.pickup_id == previous.id)))
        if previous.order_id != order.id or old != set(line_ids) or (previous.observation or '') != (observation or ''):
            raise HTTPException(409, 'Este identificador ya corresponde a otra recogida')
        return detail(db, order)
    if not line_ids or len(line_ids) != len(set(line_ids)):
        raise HTTPException(422, 'Selecciona líneas completas sin repetirlas')
    data = detail(db, order)
    if data['summary'] and data['summary']['legacy_delivery']:
        raise HTTPException(409, 'Este pedido tiene una entrega histórica sin desglose; requiere revisión antes de registrar otra')
    eligible = {line['id'] for doc in data['documents'] for line in doc['lines'] if line['can_collect']}
    if not set(line_ids) <= eligible:
        raise HTTPException(409, 'El albarán ha cambiado, alguna línea ya se recogió o requiere revisión. Actualiza antes de confirmar')
    rows = list(db.scalars(select(Line).where(Line.id.in_(line_ids))))
    totals = defaultdict(Decimal)
    for line in rows:
        totals[line.order_item_id] += line.quantity
    state_lines = {int(line['line_key']): number(line['delivered_quantity']) for line in data['summary']['lines']}
    for item_id, amount in totals.items():
        if amount + state_lines.get(item_id, Decimal(0)) > db.get(OrderItem, item_id).quantity:
            raise HTTPException(409, 'Las cantidades de los albaranes superan lo pedido; requiere revisión')
    stamp = datetime.now(timezone.utc)
    event = Pickup(order_id=order.id, request_id=request_id, confirmed_by=actor.id, confirmed_at=stamp, observation=observation)
    db.add(event); db.flush()
    for line in rows:
        db.add(Picked(pickup_id=event.id, delivery_line_id=line.id, quantity=line.quantity))
    db.flush()
    db.info.pop("pickup_summary_cache", None)
    state = summary(db, order)
    order.delivered_at = stamp if state['state'] == 'ENTREGADO_TOTAL' else None
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=state['state'], changed_by_user_id=actor.id,
                              source='WEB_PICKUP', note=f'Recogida de {len(rows)} líneas de albarán confirmada', created_at=stamp))
    return detail(db, order)


def matches_state(payload, requested, accepted):
    if requested == 'FACTURADO':
        return payload.get('estado_registro_exit') == 'FACTURADO'
    current = (payload.get('pickup_summary') or {}).get('state')
    if current:
        if requested in {'PENDIENTE_RECOJO', 'ATENDIDO'}:
            return current in {'PENDIENTE_RECOGIDA_PARCIAL', 'PENDIENTE_RECOGIDA_TOTAL'}
        if requested == 'ENTREGADO':
            return current in {'ENTREGADO_PARCIAL', 'ENTREGADO_TOTAL'}
        if requested in {'PENDIENTE_RECOGIDA_PARCIAL', 'PENDIENTE_RECOGIDA_TOTAL', 'ENTREGADO_PARCIAL', 'ENTREGADO_TOTAL'}:
            return current == requested
    return payload.get('estado_registro_exit') in accepted


def prime_summaries(db, orders):
    """Five ledger reads for a whole list, rather than five per order."""
    orders = [order for order in orders if order.pickup_managed_at]
    if not orders:
        return
    ids = [order.id for order in orders]
    buckets = {key: [[], [], [], [], []] for key in ids}
    for row in db.scalars(select(OrderItem).where(OrderItem.order_id.in_(ids))):
        buckets[row.order_id][0].append(row)
    notes = list(db.scalars(select(Note).where(Note.order_id.in_(ids))))
    note_orders = {row.id: row.order_id for row in notes}
    for row in notes:
        buckets[row.order_id][1].append(row)
    for row in db.scalars(select(Line).join(Note).where(Note.order_id.in_(ids))):
        buckets[note_orders[row.delivery_note_id]][2].append(row)
    events = list(db.scalars(select(Pickup).where(Pickup.order_id.in_(ids)).order_by(Pickup.confirmed_at, Pickup.id)))
    event_orders = {row.id: row.order_id for row in events}
    for row in events:
        buckets[row.order_id][3].append(row)
    for row in db.scalars(select(Picked).join(Pickup).where(Pickup.order_id.in_(ids))):
        buckets[event_orders[row.pickup_id]][4].append(row)
    db.info['pickup_summary_cache'] = {order.id: summary(db, order, buckets[order.id]) for order in orders}


def preview_summary(db, order, documents, remote=None):
    """Fresh public tracking calculation, without changing database rows or recording pickup."""
    from types import SimpleNamespace as Row
    items, notes, rows, events, picked = snapshot(db, order)
    items = [Row(id=item.id, sku=item.sku, unit=item.unit, quantity=item.quantity,
                 exit_line_number=item.exit_line_number, exit_removed_at=item.exit_removed_at) for item in items]
    if remote is not None and 'lines' in remote.model_fields_set:
        for item in items:
            matches = [line for line in remote.lines if line.sku == item.sku and
                       (line.line_number == item.exit_line_number if item.exit_line_number else True)]
            if item.exit_line_number or sum(other.sku == item.sku for other in items) == 1:
                if len(matches) <= 1:
                    item.exit_removed_at = None if matches else True
    old_notes = {(note.company_code, note.year, note.series, note.number): note for note in notes}
    old_lines = {(row.delivery_note_id, row.line_number): row for row in rows}
    collected = {row.delivery_line_id for row in picked}
    # Physical pickup evidence is retained even if EXIT no longer contains its note.
    preview_rows = [Row(**{key: getattr(row, key) for key in ('id','delivery_note_id','order_item_id','sku','unit','quantity','warning')}, current=False) for row in rows if row.id in collected]
    preview_notes = {note.id: Row(id=note.id, current=False, status=note.status) for note in notes}
    for index, doc in enumerate(documents):
        if not matches_note(doc, order):
            continue
        parts = str(doc.get('number') or '').replace('~','/').replace('-','/').split('/')
        if len(parts) != 3 or not parts[0].isdigit():
            raise ValueError('Albarán sin llave completa')
        key = (int(doc['company_code']),int(parts[0]),parts[1].strip().upper(),parts[2])
        old_note = old_notes.get(key)
        note_id = old_note.id if old_note else -index-1
        preview_notes[note_id] = Row(id=note_id,current=True,status=doc.get('status'))
        seen = set()
        for position, source in enumerate(doc.get('items', [])):
            line_number = str(source.get('line') or '')
            if not line_number or line_number in seen:
                raise ValueError('Líneas de albarán ambiguas')
            seen.add(line_number)
            old_line = old_lines.get((note_id,line_number))
            if old_line and old_line.id in collected:
                continue
            sku, unit = str(source.get('sku') or '').strip(), str(source.get('unit') or 'UD').strip().upper()
            candidates = [item for item in items if item.sku == sku and item.unit.strip().upper() == unit]
            if source.get('order_line_number') is not None:
                candidates = [item for item in candidates if item.exit_line_number == str(source['order_line_number'])]
            target = candidates[0] if len(candidates) == 1 else None
            quantity = number(source.get('quantity'))
            preview_rows.append(Row(id=old_line.id if old_line else -(1000000+index*10000+position),delivery_note_id=note_id,
                order_item_id=target.id if target else None,sku=sku,unit=unit,quantity=quantity,current=True,
                warning=None if target and not target.exit_removed_at and quantity > 0 else 'Requiere revisión'))
    ephemeral = Row(id=order.id,pickup_managed_at=True,delivered_at=order.delivered_at)
    return summary(db, ephemeral, (items,list(preview_notes.values()),preview_rows,events,picked))


def has_pickups(db, order):
    return db.scalar(select(Pickup.id).where(Pickup.order_id == order.id).limit(1)) is not None


def receipt_order_keys(db, orders):
    if not orders:
        return []
    collected = set(db.scalars(select(Pickup.order_id).where(Pickup.order_id.in_([order.id for order in orders])).distinct()))
    return [key for order in orders if order.id in collected and (key := order_key(order))]
