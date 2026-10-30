"""Delivery notes must reference the full sales-order key, including company."""
from .exit_order_key import stored_key, record_key


def normalize_key(values):
    if values is None or len(values)!=4 or any(value is None for value in values):
        return None
    company,year,series,number=values
    if not str(number).strip():return None
    try:
        return int(company),int(year),str(series).strip().upper(),str(number).strip()
    except (TypeError,ValueError):
        return None


def note_order_key(note):
    company=note.get('exit_company_code') if note.get('exit_company_code') is not None else note.get('company_code')
    values=(company,note.get('exit_order_year'),note.get('exit_series'),note.get('exit_order_number'))
    full=normalize_key(values)
    if full:return full
    if any(note.get(field) is not None for field in ('exit_order_year','exit_series','exit_order_number')):
        return None
    # Older producers can format the three document components, but must identify company.
    reference=str(note.get('order_number') or note.get('exit_number') or note.get('nro_pedido_exit') or '').replace('~','/')
    if '/' not in reference and len(reference.split('-',2))==3:reference=reference.replace('-','/',2)
    parts=reference.split('/')
    return normalize_key((company,*parts)) if len(parts)==3 else None


def order_key(order):
    return normalize_key(stored_key(order))


def live_order_key(record):
    return normalize_key(record_key(record))


def matches_note(note,order):
    expected=order_key(order)
    return expected is not None and note_order_key(note)==expected


def source_order_fields(row):
    return {'company_code':row.get('CodigoEmpresa'), 'exit_company_code':row.get('CodigoEmpresa'),
            'exit_order_year':row.get('EjercicioPedido'),
            'exit_series':str(row['SeriePedido']).strip() if row.get('SeriePedido') is not None else None,
            'exit_order_number':str(row['NumeroPedido']).strip() if row.get('NumeroPedido') is not None else None}
