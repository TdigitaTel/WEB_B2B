import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def public_uuid() -> str:
    return str(uuid.uuid4())


class SyncStatus(str, enum.Enum):
    pending = "PENDING"
    synced = "SYNCED"
    error = "ERROR"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_uuid)
    erp_id: Mapped[str] = mapped_column(String(40), unique=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str] = mapped_column(String(160))
    tax_id: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40))
    billing_address: Mapped[str] = mapped_column(Text)
    price_list: Mapped[str] = mapped_column(String(30), default="PROFESIONAL")
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    usual_store_id: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.pending)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    erp_customer_code: Mapped[str | None] = mapped_column(String(40), index=True)
    store_id: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer: Mapped[Customer | None] = relationship()


class ProfessionalRegistrationRequest(Base, TimestampMixin):
    __tablename__ = "professional_registration_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_uuid)
    legal_name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str] = mapped_column(String(20), index=True)
    contact_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="PENDIENTE", index=True)
    accepted_terms: Mapped[bool] = mapped_column(Boolean)


class Brand(Base, TimestampMixin):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)


class MaterialArea(Base, TimestampMixin):
    __tablename__ = "material_areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)


class MaterialFamily(Base, TimestampMixin):
    __tablename__ = "material_families"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    area_id: Mapped[int] = mapped_column(ForeignKey("material_areas.id"), index=True)
    __table_args__ = (UniqueConstraint("area_id", "name"),)


class MaterialSubfamily(Base, TimestampMixin):
    __tablename__ = "material_subfamilies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    family_id: Mapped[int] = mapped_column(ForeignKey("material_families.id"), index=True)
    __table_args__ = (UniqueConstraint("family_id", "name"),)


class MaterialProductType(Base, TimestampMixin):
    __tablename__ = "material_product_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    subfamily_id: Mapped[int] = mapped_column(ForeignKey("material_subfamilies.id"), index=True)
    __table_args__ = (UniqueConstraint("subfamily_id", "name"),)


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_uuid)
    erp_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    manufacturer_reference: Mapped[str] = mapped_column(String(80), index=True)
    ean: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    material_area_id: Mapped[int | None] = mapped_column(ForeignKey("material_areas.id"), index=True)
    material_family_id: Mapped[int | None] = mapped_column(ForeignKey("material_families.id"), index=True)
    material_subfamily_id: Mapped[int | None] = mapped_column(ForeignKey("material_subfamilies.id"), index=True)
    material_product_type_id: Mapped[int | None] = mapped_column(ForeignKey("material_product_types.id"), index=True)
    family: Mapped[str] = mapped_column(String(100), index=True)
    subfamily: Mapped[str] = mapped_column(String(100), index=True)
    short_description: Mapped[str] = mapped_column(String(240))
    original_description: Mapped[str | None] = mapped_column(Text)
    commercial_description: Mapped[str] = mapped_column(Text)
    technical_description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20), default="UD")
    pack_size: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    list_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=21)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized_search: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.pending)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classification_status: Mapped[str | None] = mapped_column(String(50), index=True)
    classification_reason: Mapped[str | None] = mapped_column(Text)
    classification_confidence: Mapped[str | None] = mapped_column(String(30), index=True)
    source_system: Mapped[str | None] = mapped_column(String(40), index=True)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    image_media_type: Mapped[str | None] = mapped_column(String(80))
    image_source_url: Mapped[str | None] = mapped_column(Text)
    image_source_provider: Mapped[str | None] = mapped_column(String(160))
    image_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    brand: Mapped[Brand] = relationship()
    category: Mapped[Category] = relationship()
    __table_args__ = (Index("ix_products_family_active", "family", "active"),)


class ProductImageMissing(Base, TimestampMixin):
    """Cola auditable de materiales cuya imagen aún no está en PostgreSQL."""

    __tablename__ = "product_image_missing"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, index=True
    )
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDIENTE", index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class MaterialImportRow(Base, TimestampMixin):
    """Copia auditable de cada fila del Excel, incluidos duplicados."""
    __tablename__ = "material_import_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(240))
    source_sheet: Mapped[str] = mapped_column(String(120))
    source_row: Mapped[int] = mapped_column(Integer)
    article_code: Mapped[str] = mapped_column(String(80), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("source_file", "source_sheet", "source_row"),)


class Cart(Base, TimestampMixin):
    __tablename__ = "carts"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_uuid)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    customer_code: Mapped[str | None] = mapped_column(String(40), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    store_id: Mapped[str | None] = mapped_column(String(40))


class CartItem(Base, TimestampMixin):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    __table_args__ = (UniqueConstraint("cart_id", "product_id"),)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_uuid)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    customer_code: Mapped[str | None] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    store_id: Mapped[str] = mapped_column(String(40), index=True)
    nro_pedido_exit: Mapped[str | None] = mapped_column(String(80), index=True)
    fecha_registro_exit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origen_pedido: Mapped[str] = mapped_column(String(20), default="B2B", index=True)
    estado_registro_exit: Mapped[str] = mapped_column(String(80), default="PENDIENTE", index=True)
    customer_reference: Mapped[str | None] = mapped_column(String(100))
    job_name: Mapped[str | None] = mapped_column(String(160), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    sync_status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.pending)
    __table_args__ = (
        Index("ix_orders_store_created", "store_id", "created_at"),
        Index("ux_orders_nro_pedido_exit", "nro_pedido_exit", unique=True),
    )


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(20))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fulfillment_zone: Mapped[str | None] = mapped_column(String(20), index=True)
    served_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    pending_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    estado_registro_exit: Mapped[str] = mapped_column(String(80), index=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(20), default="WEB")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    customer_code: Mapped[str | None] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrationOutbox(Base):
    __tablename__ = "integration_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[str] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    sync_status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.pending, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
