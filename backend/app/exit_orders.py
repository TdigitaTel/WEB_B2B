"""Proyección idempotente de pedidos EXIT para la bandeja de operación.

El futuro demonio solo debe transformar cada registro de cabecera/detalle de EXIT al
contrato ``ExitOrderInput`` y llamar ``upsert_exit_order`` dentro de una transacción.
No contiene nombres de tablas de EXIT porque todavía deben ser confirmados.
"""
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .delegations import resolve_delegation
from .models import Order, OrderItem, OrderStatusHistory, Product, SyncStatus, User


class ExitOrderLineInput(BaseModel):
    line_number: str | None = None
    sku: str
    description: str
    quantity: Decimal = Field(gt=0)
    unit: str = "UD"
    unit_price: Decimal = Decimal("0")
    discount_pct: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("21")
    net_amount: Decimal | None = None
    line_total: Decimal | None = None
    fulfillment_zone: str = "OTROS"
    served_quantity: Decimal | None = None
    pending_quantity: Decimal | None = None


class ExitOrderInput(BaseModel):
    exit_order_id: str
    exit_company_code: int | None = None
    exit_order_year: int | None = None
    exit_series: str | None = None
    exit_order_number: str | None = None
    web_order_number: str | None = None
    order_number: str
    customer_code: str
    store_code: str
    company_code: int | None = None
    estado_registro_exit: str
    source_status: str | None = None
    source_created_by: str | None = None
    source_updated_at: datetime
    recorded_at: datetime | None = None
    prepared_at: datetime | None = None
    delivered_at: datetime | None = None
    invoiced_at: datetime | None = None
    customer_reference: str | None = None
    auxiliary_reference: str | None = None
    job_name: str | None = None
    notes: str | None = None
    subtotal: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    lines: list[ExitOrderLineInput] = Field(default_factory=list)


def reconcile_exit_lines(db: Session, order: Order, lines: list[ExitOrderLineInput]) -> None:
    """Retain the WEB snapshot and persistent line IDs; EXIT only updates fulfilment.

    Line numbers are scoped by the parent order (which holds the four EXIT keys).
    Legacy lines can be linked by SKU only when unambiguous. Ambiguous legacy
    groups remain untouched until EXIT provides enough information to link them.
    This function requires a complete, successfully read order detail, never a
    filtered or failed query.
    """
    numbers = [line.line_number for line in lines if line.line_number]
    if len(numbers) != len(set(numbers)):
        raise ValueError("EXIT devuelve números de línea duplicados; se conserva el detalle WEB")
    db.scalar(select(Order).where(Order.id == order.id).with_for_update())
    existing = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)
                              .order_by(OrderItem.id).with_for_update()))
    skus = {line.sku for line in lines}
    products = {p.sku: p for p in db.scalars(select(Product).where(Product.sku.in_(skus)))} if skus else {}
    matched = set()
    protected = set()
    assignments = []
    remaining = []
    for line in lines:
        exact = [item for item in existing if item.id not in matched and line.line_number
                 and item.exit_line_number == line.line_number and item.sku == line.sku]
        if len(exact) == 1:
            matched.add(exact[0].id)
            assignments.append((exact[0], line))
        else:
            remaining.append(line)
    for sku in {line.sku for line in remaining}:
        incoming = [line for line in remaining if line.sku == sku]
        candidates = [item for item in existing if item.id not in matched and item.sku == sku
                      and (not item.exit_line_number or any(not line.line_number for line in incoming))]
        if len(candidates) == len(incoming) == 1:
            pairs = [(candidates[0], incoming[0])]
        elif candidates:
            # Do not arbitrarily retire one of several identical, unnumbered WEB lines.
            def signature(row):
                return (row.description, row.quantity, row.unit, row.unit_price)
            if len(candidates) == len(incoming) and sorted(map(signature, candidates)) == sorted(map(signature, incoming)):
                available = candidates.copy()
                pairs = []
                for line in incoming:
                    item = next(item for item in available if signature(item) == signature(line))
                    available.remove(item)
                    pairs.append((item, line))
            else:
                protected.update(item.id for item in candidates)
                continue
        else:
            pairs = [(None, line) for line in incoming]
        for item, line in pairs:
            if item is not None:
                matched.add(item.id)
            assignments.append((item, line))
    for item, line in assignments:
        if item is None:
            product = products.get(line.sku)
            item = OrderItem(order_id=order.id, created_in_web=False, product_id=product.id if product else None,
                             sku=line.sku, description=line.description, quantity=line.quantity,
                             unit=line.unit, unit_price=line.unit_price, discount_pct=line.discount_pct,
                             tax_rate=line.tax_rate,
                             line_total=line.line_total if line.line_total is not None else line.quantity * line.unit_price)
            db.add(item)
        item.exit_entered_at = item.exit_entered_at or datetime.now(timezone.utc)
        item.exit_line_number = line.line_number or item.exit_line_number
        item.exit_removed_at = None
        item.fulfillment_zone = line.fulfillment_zone
        item.served_quantity = line.served_quantity
        item.pending_quantity = line.pending_quantity
    now = datetime.now(timezone.utc)
    for item in existing:
        if item.id not in matched and item.id not in protected:
            # Keep the last quantities, prices, text, manual planning and timestamp.
            item.exit_removed_at = item.exit_removed_at or now
    db.flush()


def upsert_exit_order(db: Session, incoming: ExitOrderInput, integration_user: User) -> Order:
    """Crea/actualiza la proyección local. Repetir el mismo registro no lo duplica."""
    store = resolve_delegation(incoming.store_code, company_code=incoming.company_code)
    if not store:
        raise ValueError(f"Almacén interno desconocido: {incoming.store_code}")
    estado_registro_exit = incoming.estado_registro_exit.strip().upper()
    if estado_registro_exit not in {"PENDIENTE", "REGISTRADO", "EN_PROCESO", "EN_PREPARACION", "ATENDIDO", "ENTREGADO", "FACTURADO"}:
        raise ValueError(f"Estado EXIT no mapeado: {incoming.estado_registro_exit}")

    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"exit-order:{incoming.exit_order_id}"})
    from .exit_order_key import record_key, stored_key, FIELDS
    identity = record_key(incoming)
    candidates = db.scalars(select(Order).where(Order.company_code == store.company, Order.customer_code == incoming.customer_code)).all()
    matches = [row for row in candidates if (identity and stored_key(row) == identity) or row.nro_pedido_exit == incoming.exit_order_id]
    order = next((row for row in matches if row.origen_pedido == 'B2B'), matches[0] if len(matches) == 1 else None)
    if not order and incoming.web_order_number:
        order = db.scalar(select(Order).where(Order.order_number == incoming.web_order_number, Order.company_code == store.company, Order.customer_code == incoming.customer_code))
    if order and identity and stored_key(order) != identity:
        from .models import OrderPickup
        if db.scalar(select(OrderPickup.id).where(OrderPickup.order_id == order.id).limit(1)):
            raise ValueError('El pedido tiene recogidas registradas y no se puede cambiar su llave EXIT')
    is_new = order is None
    if is_new:
        order = Order(
            order_number=incoming.order_number,
            customer_id=None,
            customer_code=incoming.customer_code,
            user_id=integration_user.id,
            company_code=store.company, delegation_code=store.code,
            nro_pedido_exit=incoming.exit_order_id,
            fecha_registro_exit=incoming.recorded_at,
            origen_pedido="EXIT",
            estado_registro_exit=estado_registro_exit,
            sync_status=SyncStatus.synced,
        )
        db.add(order)
        db.flush()
    # Las unidades pendientes viven en el detalle de EXIT y pueden cambiar sin que
    # la fecha de modificación de la cabecera avance. Por eso se refrescan siempre
    # las líneas del pedido durante la sincronización.

    from .order_timeline import is_web_order
    web_order = is_web_order(incoming, order)
    if estado_registro_exit == "ENTREGADO" and web_order:
        estado_registro_exit = "ATENDIDO"
    if identity:
        for field, value in zip(FIELDS, identity):
            setattr(order, field, value)
    order.nro_pedido_exit = incoming.exit_order_id
    order.fecha_registro_exit = incoming.recorded_at or order.fecha_registro_exit
    order.estado_registro_exit = "ENTREGADO" if order.delivered_at and estado_registro_exit != "FACTURADO" else estado_registro_exit
    if is_new:
        order.origen_pedido = "EXIT"
    if is_new and incoming.recorded_at:
        order.created_at = incoming.recorded_at
    order.customer_code = incoming.customer_code
    order.company_code = store.company
    order.delegation_code = store.code
    order.customer_reference = incoming.customer_reference
    order.job_name = incoming.job_name
    order.notes = incoming.notes
    order.subtotal = incoming.subtotal
    order.tax_total = incoming.tax_total
    order.total = incoming.total
    order.sync_status = SyncStatus.synced

    if "lines" in incoming.model_fields_set:
        reconcile_exit_lines(db, order, incoming.lines)
    from .order_timeline import exit_events, sync_history
    sync_history(db, order, exit_events(incoming, web_order=web_order), web_order=web_order)
    return order


def import_exit_batch(db: Session, records: list[ExitOrderInput], integration_user: User, cursor_value: str) -> int:
    """Compatibilidad manual para importar una página sin cursor persistente."""
    for record in records:
        upsert_exit_order(db, record, integration_user)
    db.commit()
    return len(records)
