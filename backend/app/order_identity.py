"""Match customer history projections without confusing company, series or year."""
import re
from .exit_order_key import stored_key, record_key


def document_parts(value):
    value = str(value or "").strip().upper().replace("~", "/")
    if "/" not in value and re.match(r"^\d{4}-", value):
        return tuple(part.strip() for part in value.split("-", 2))
    return tuple(part.strip() for part in value.split("/")) if value else ()


def same_scope(row, record):
    return (row.customer_code == record.customer_code
            and row.company_code == record.company_code
            and row.delegation_code == record.store_code)


def matches_document(row, record):
    local_key, remote_key = stored_key(row), record_key(record)
    if local_key and remote_key:
        return local_key == remote_key
    left, right = document_parts(row.nro_pedido_exit), document_parts(record.exit_order_id)
    if not left or not right:
        return False
    if left == right:
        return True
    # A full identity never matches a different year or series just by its number.
    if len(left) == 1 and len(right) == 3 and left[0] == right[-1]:
        stamp = row.fecha_registro_exit or row.created_at
        return bool(stamp and str(stamp.year) == right[0])
    return False


def linked_customer_order(rows, record, records):
    candidates = [row for row in rows if same_scope(row, record)]
    reference = str(record.web_order_number or record.customer_reference or "").strip().upper()
    referenced = [row for row in candidates if row.origen_pedido == "B2B"
                  and row.order_number.strip().upper() == reference
                  and (not row.nro_pedido_exit or matches_document(row, record))]
    matching = []
    for row in candidates:
        if not matches_document(row, record):
            continue
        if len(document_parts(row.nro_pedido_exit)) == 1:
            identities = {document_parts(other.exit_order_id) for other in records
                          if same_scope(row, other) and matches_document(row, other)}
            if len(identities) > 1 and row not in referenced:
                continue  # A short number cannot identify one of several series.
        matching.append(row)
    web = referenced or [row for row in matching if row.origen_pedido == "B2B"]
    if len(web) == 1:
        # Existing EXIT projections remain stored, but are represented by the web row.
        return web[0], [row for row in matching if row.origen_pedido != "B2B"]
    exact = [row for row in matching if document_parts(row.nro_pedido_exit) == document_parts(record.exit_order_id)]
    return (exact[0], []) if len(exact) == 1 else (None, [])


def customer_history_without_shadows(payloads):
    """Hide old local EXIT projections without deleting stored data."""
    def scope(row):
        return tuple(row.get(key) for key in ("customer_code", "company_code", "delegation_code"))
    def identity(row):
        return document_parts(row.get("exit_number") or row.get("nro_pedido_exit"))
    web_full, web_short, full_groups = set(), set(), {}
    for row in payloads:
        parts, seat = identity(row), scope(row)
        if len(parts) == 3:
            full_groups.setdefault((seat, parts[0], parts[-1]), set()).add(parts)
        if row.get("origen_pedido") != "B2B" or not parts:
            continue
        if len(parts) == 1:
            stamp = row.get("fecha_registro_exit") or row.get("created_at")
            year = str(getattr(stamp, "year", str(stamp or "")[:4]))
            web_short.add((seat, year, parts[0]))
        else:
            web_full.add((seat, parts))
    result = []
    for row in payloads:
        parts, seat = identity(row), scope(row)
        duplicate = (seat, parts) in web_full if parts else False
        if len(parts) == 3:
            group = (seat, parts[0], parts[-1])
            duplicate = duplicate or (group in web_short and len(full_groups[group]) == 1)
        if row.get("origen_pedido") == "B2B" or not duplicate:
            result.append(row)
    return result
