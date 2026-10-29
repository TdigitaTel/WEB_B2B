"""Structured EXIT identity. The legacy text reference is for compatibility only."""
from fastapi import HTTPException
from sqlalchemy import select, text
from .models import Order

FIELDS = ('exit_company_code', 'exit_order_year', 'exit_series', 'exit_order_number')


def parts(value):
    value = str(value or '').strip().upper().replace('~', '/')
    return value.split('/')


def stored_key(order):
    values = tuple(getattr(order, field, None) for field in FIELDS)
    if all(value is not None for value in values):
        return values
    # Read old records during the RPA transition; do not guess their series/year.
    legacy = parts(order.nro_pedido_exit)
    if len(legacy) == 3 and legacy[0].isdigit():
        return order.company_code, int(legacy[0]), legacy[1], legacy[2]
    return None


def record_key(record):
    values = tuple(getattr(record, field, None) for field in FIELDS)
    if all(value is not None for value in values):
        return values
    legacy = parts(record.exit_order_id)
    if len(legacy) == 3 and legacy[0].isdigit() and record.company_code is not None:
        return record.company_code, int(legacy[0]), legacy[1], legacy[2]
    return None


def key_payload(order):
    return {field: getattr(order, field, None) for field in FIELDS}


def apply_key(db, order, supplied, legacy=None, validate_number=True):
    supplied = dict(supplied)
    old_number = supplied.get('exit_order_number')
    if old_number and ('/' in old_number or '~' in old_number) and not any(supplied.get(field) is not None for field in FIELDS[:3]):
        legacy = legacy or old_number
        supplied.pop('exit_order_number')  # Old manual clients sent a formatted reference here.
    before = key_payload(order), order.nro_pedido_exit
    values = key_payload(order)
    values.update({field: supplied[field] for field in FIELDS if field in supplied and supplied[field] is not None})
    if 'exit_series' in values and values['exit_series'] is not None:
        values['exit_series'] = values['exit_series'].strip().upper()
    structured = any(field in supplied and supplied[field] is not None for field in FIELDS)
    if validate_number and structured and supplied.get('exit_order_number') is not None and not supplied['exit_order_number'].strip().isdigit():
        raise HTTPException(422, 'El número de pedido debe contener solo dígitos; empresa, ejercicio y serie van separados')
    if values['exit_company_code'] is not None and values['exit_company_code'] != order.company_code:
        raise HTTPException(422, 'La empresa EXIT debe coincidir con la empresa del pedido')
    if values['exit_order_number'] is not None:
        values['exit_order_number'] = values['exit_order_number'].strip()
    full = all(value is not None for value in values.values())
    identity = tuple(values[field] for field in FIELDS) if full else None
    if db.bind.dialect.name == 'postgresql':
        lock = repr(identity) if identity else f'order:{order.id}'
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'exit-key:'+lock})
    reference = legacy.strip().replace('~','/').upper() if legacy else None
    if identity:
        reference = f'{identity[1]}/{identity[2]}/{identity[3]}'
    if reference:
        peers = db.scalars(select(Order).where(Order.id != order.id, Order.company_code == order.company_code)).all()
        for peer in peers:
            same = stored_key(peer) == identity if identity else peer.nro_pedido_exit == reference
            if not same:
                continue
            if peer.origen_pedido == 'B2B':
                raise HTTPException(409, 'Esa llave EXIT ya está vinculada a otro pedido WEB')
            if identity and stored_key(peer) == identity:
                # Transfer ownership of the structured key to the original web order.
                for field in FIELDS[1:]:
                    setattr(peer, field, None)
                db.flush()
        order.nro_pedido_exit = reference
    for field, value in values.items():
        setattr(order, field, value)
    return before != (key_payload(order), order.nro_pedido_exit)
