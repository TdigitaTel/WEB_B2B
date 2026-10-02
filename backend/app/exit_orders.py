"""Proyección idempotente de pedidos EXIT para la bandeja de operación.

El futuro demonio solo debe transformar cada registro de cabecera/detalle de EXIT al
contrato ``ExitOrderInput`` y llamar ``upsert_exit_order`` dentro de una transacción.
No contiene nombres de tablas de EXIT porque todavía deben ser confirmados.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Order, OrderItem, OrderStatusHistory, Product, Store, SyncStatus, User


class ExitOrderLineInput(BaseModel):
    sku: str
    description: str
    quantity: Decimal = Field(gt=0)
    unit: str = "UD"
    unit_price: Decimal = Decimal("0")
    discount_pct: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("21")
    line_total: Decimal | None = None
    fulfillment_zone: str = "OTROS"
    served_quantity: Decimal | None = None
    pending_quantity: Decimal | None = None


class ExitOrderInput(BaseModel):
    exit_order_id: str
    web_order_number: str | None = None
    order_number: str
    customer_code: str
    store_code: str
    estado_registro_exit: str
    source_status: str | None = None
    source_created_by: str | None = None
    source_updated_at: datetime
    recorded_at: datetime | None = None
    customer_reference: str | None = None
    auxiliary_reference: str | None = None
    job_name: str | None = None
    notes: str | None = None
    subtotal: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    lines: list[ExitOrderLineInput] = Field(default_factory=list)


def upsert_exit_order(db: Session, incoming: ExitOrderInput, integration_user: User) -> Order:
    """Crea/actualiza la proyección local. Repetir el mismo registro no lo duplica."""
    store = db.scalar(select(Store).where(Store.code == incoming.store_code, Store.active.is_(True)))
    if not store:
        raise ValueError(f"Almacén interno desconocido: {incoming.store_code}")
    estado_registro_exit = incoming.estado_registro_exit.strip().upper()
    if estado_registro_exit not in {"PENDIENTE", "REGISTRADO", "EN_PROCESO", "ATENDIDO", "ENTREGADO", "FACTURADO"}:
        raise ValueError(f"Estado EXIT no mapeado: {incoming.estado_registro_exit}")

    order = db.scalar(select(Order).where(Order.nro_pedido_exit == incoming.exit_order_id))
    if not order and incoming.web_order_number:
        order = db.scalar(select(Order).where(Order.order_number == incoming.web_order_number))
    is_new = order is None
    if is_new:
        order = Order(
            order_number=incoming.order_number,
            customer_id=None,
            customer_code=incoming.customer_code,
            user_id=integration_user.id,
            store_id=store.id,
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

    previous_status = order.estado_registro_exit
    first_exit_registration = is_new or not order.nro_pedido_exit
    order.nro_pedido_exit = incoming.exit_order_id
    order.fecha_registro_exit = incoming.recorded_at or order.fecha_registro_exit
    order.estado_registro_exit = estado_registro_exit
    if is_new:
        order.origen_pedido = "EXIT"
    if incoming.recorded_at:
        order.created_at = incoming.recorded_at
    order.customer_code = incoming.customer_code
    order.store_id = store.id
    order.customer_reference = incoming.customer_reference
    order.job_name = incoming.job_name
    order.notes = incoming.notes
    order.subtotal = incoming.subtotal
    order.tax_total = incoming.tax_total
    order.total = incoming.total
    order.sync_status = SyncStatus.synced

    db.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    skus = [line.sku for line in incoming.lines]
    products = {p.sku: p for p in db.scalars(select(Product).where(Product.sku.in_(skus))).all()} if skus else {}
    for line in incoming.lines:
        line_total = line.line_total if line.line_total is not None else (line.quantity * line.unit_price)
        db.add(OrderItem(order_id=order.id, product_id=products.get(line.sku).id if products.get(line.sku) else None,
                         sku=line.sku, description=line.description, quantity=line.quantity, unit=line.unit,
                         unit_price=line.unit_price, discount_pct=line.discount_pct, tax_rate=line.tax_rate,
                         line_total=line_total, fulfillment_zone=line.fulfillment_zone,
                         served_quantity=line.served_quantity, pending_quantity=line.pending_quantity))
    if first_exit_registration:
        registered_at = incoming.recorded_at or incoming.source_updated_at
        exit_steps = ["REGISTRADO", "EN_PROCESO", "ATENDIDO", "ENTREGADO", "FACTURADO"]
        steps_to_record = (exit_steps[:exit_steps.index(estado_registro_exit) + 1]
                           if estado_registro_exit in exit_steps else [estado_registro_exit])
        for step in steps_to_record:
            db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=step,
                                      changed_by_user_id=integration_user.id, source="EXIT",
                                      note="Estado recibido desde EXIT", created_at=registered_at))
    elif previous_status != estado_registro_exit:
        db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=estado_registro_exit, changed_by_user_id=integration_user.id, source="EXIT",
                                  note="Estado recibido desde EXIT", created_at=incoming.source_updated_at))
    return order


def import_exit_batch(db: Session, records: list[ExitOrderInput], integration_user: User, cursor_value: str) -> int:
    """Compatibilidad manual para importar una página sin cursor persistente."""
    for record in records:
        upsert_exit_order(db, record, integration_user)
    db.commit()
    return len(records)
